"""Synthetic regression cases, not evidence of factor validity."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research_core.factor_lab import deterministic_validation as dv


def _config():
    config = dv.load_validation_config(
        Path(__file__).resolve().parents[1] / "configs/validation_gates.yaml"
    )
    config["factor"]["definitions"]["turnover_20d"]["window"] = 2
    config["styles"].update(
        momentum_window=1, volatility_window=2, volatility_minimum_periods=2,
        liquidity_window=2, liquidity_minimum_periods=2,
    )
    config["forward_returns"].update(horizons=[1, 2], primary_horizon=1)
    config["split"].update(train_start="2024-01-01", train_end="2024-01-05")
    return config


def _panel():
    dates = pd.bdate_range("2024-01-01", periods=5)
    frames = []
    for code in ("A", "B"):
        close = np.array([100., 90., 110., 120., 125.])
        frames.append(pd.DataFrame({
            "date": dates, "code": code, "close": close,
            "volume": 100., "total_turnover": [10., 20., 40., 80., 160.],
            "turnover_rate": [1., 2., 4., 8., 16.],
            "limit_up": close * 1.1, "limit_down": close * .9,
            "circulation_a": 100000., "listed_date": pd.Timestamp("2000-01-01"),
            "de_listed_date": pd.NaT, "is_st": False, "is_suspended": False,
        }))
    return pd.concat(frames, ignore_index=True)


def _training_frame(panel, monkeypatch):
    # Inspect real preprocessing at the statistics boundary, without needing
    # a large cross-section or replacing any temporal calculation.
    captured = {}

    def capture(train, clean, config, **kwargs):
        captured["train"] = train
        return {"status": "train_only"}

    monkeypatch.setattr(dv, "_training_segment_result", capture)
    dv.validate_panel(panel, "turnover_20d", _config(), segment="train")
    return captured["train"].set_index(["code", "date"]).sort_index()


@pytest.mark.parametrize("restriction", ["is_st", "is_suspended", "limit_up", "limit_down"])
def test_future_eligibility_does_not_select_return_endpoint(restriction, monkeypatch):
    panel = _panel()
    date = panel["date"].sort_values().unique()[1]
    row = (panel["code"] == "A") & panel["date"].eq(date)
    if restriction.startswith("is_"):
        panel.loc[row, restriction] = True
    else:
        panel.loc[row, restriction] = panel.loc[row, "close"]
    result = _training_frame(panel, monkeypatch)
    first = result.loc[("A", pd.Timestamp("2024-01-01"))]
    assert first["target_date_1d"] == pd.Timestamp("2024-01-02")
    assert first["forward_return_1d"] == pytest.approx(-.1)
    assert ("A", pd.Timestamp("2024-01-02")) not in result.index


def test_missing_target_observation_does_not_shift_horizon():
    panel = _panel().drop(index=1)
    result = dv._attach_forward_returns(panel, [1, 2]).set_index(["code", "date"])
    first = result.loc[("A", pd.Timestamp("2024-01-01"))]
    assert first["target_date_1d"] == pd.Timestamp("2024-01-02")
    assert pd.isna(first["forward_return_1d"])
    assert first["target_date_2d"] == pd.Timestamp("2024-01-03")
    assert first["forward_return_2d"] == pytest.approx(.1)


def test_filtered_history_does_not_compress_factor_or_style_window(monkeypatch):
    panel = _panel()
    panel.loc[1, "is_st"] = True
    result = _training_frame(panel, monkeypatch)
    third = result.loc[("A", pd.Timestamp("2024-01-03"))]
    assert third["factor_value"] == pytest.approx(3.)
    assert third["momentum"] == pytest.approx(110 / 90 - 1)
    assert third["liquidity"] == pytest.approx(np.log(30.))


def test_missing_session_is_not_replaced_by_older_factor_observation():
    panel = _panel().drop(index=1)
    values = dv._factor_lookup(panel, "turnover_20d", _config())
    assert pd.isna(values.loc[(pd.Timestamp("2024-01-03"), "A")])


@pytest.mark.parametrize("price", [0., -1., np.nan, np.inf])
def test_invalid_target_price_is_unmeasured(price):
    panel = _panel()
    panel.loc[1, "close"] = price
    result = dv._attach_forward_returns(panel, [1]).set_index(["code", "date"])
    first = result.loc[("A", pd.Timestamp("2024-01-01"))]
    assert pd.isna(first["forward_return_1d"])
    assert first["target_date_1d"] == pd.Timestamp("2024-01-02")


def test_duplicate_normalized_keys_are_rejected(monkeypatch):
    panel = _panel()
    duplicate = panel.iloc[[0]].copy()
    duplicate["date"] += pd.Timedelta(hours=1)
    with pytest.raises(ValueError, match="Duplicate"):
        _training_frame(pd.concat([panel, duplicate], ignore_index=True), monkeypatch)


def test_preprocessing_is_invariant_to_input_order_and_index(monkeypatch):
    panel = _panel()
    panel.loc[1, "is_suspended"] = True
    expected = _training_frame(panel, monkeypatch)
    shuffled = panel.sample(frac=1, random_state=7)
    shuffled.index = np.arange(len(shuffled)) * 3
    actual = _training_frame(shuffled, monkeypatch)
    pd.testing.assert_frame_equal(actual, expected)


def test_training_labels_do_not_cross_segment_boundary(monkeypatch):
    result = _training_frame(_panel(), monkeypatch)
    last = result.loc[("A", pd.Timestamp("2024-01-05"))]
    assert pd.isna(last["forward_return_1d"])
    assert pd.isna(last["forward_return_2d"])


def test_style_windows_preserve_missing_sessions():
    panel = _panel().drop(index=1)
    styles = dv._build_styles(panel, _config()).set_index(["code", "date"])
    third = styles.loc[("A", pd.Timestamp("2024-01-03"))]
    assert pd.isna(third["momentum"])
    assert pd.isna(third["liquidity"])
    assert pd.isna(third["volatility"])


def test_perturbation_uses_unfiltered_history(monkeypatch):
    config = _config()
    config["statistics"]["minimum_ic_cross_section"] = 2
    config["portfolio"].update(quantiles=2, rebalance_stride=1)
    config["split"].update(
        train_end="2024-01-09", oos_start="2024-01-10", oos_end="2024-01-19",
    )
    config["perturbation"]["multipliers"] = [2.]
    dates = pd.bdate_range("2024-01-01", periods=15)
    frames = []
    for i, code in enumerate(("A", "B")):
        frame = _panel().iloc[:5].copy()
        frame = frame.iloc[np.arange(15) % 5].reset_index(drop=True)
        frame["date"] = dates
        frame["code"] = code
        frame["close"] = 100 * (1.01 + i * .01) ** np.arange(15)
        frame["limit_up"] = frame["close"] * 1.1
        frame["limit_down"] = frame["close"] * .9
        frame["turnover_rate"] = (np.arange(15) + 1.) * (i + 1)
        frames.append(frame)
    panel = pd.concat(frames, ignore_index=True)
    panel.loc[8, "is_st"] = True
    real_ic = dv._daily_rank_ic
    captured = {}

    def observe(frame, factor_col, return_col, **kwargs):
        if factor_col == "perturbed_factor":
            captured["frame"] = frame.set_index(["code", "date"])
        return real_ic(frame, factor_col, return_col, **kwargs)

    monkeypatch.setattr(dv, "_daily_rank_ic", observe)
    dv.validate_panel(panel, "turnover_20d", config)
    assert captured["frame"].loc[("A", dates[9]), "perturbed_factor"] == pytest.approx(8.5)
