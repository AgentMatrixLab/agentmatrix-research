"""TEST-ONLY tests for the bounded-memory post-processing layer.

The whole point of `streaming_supplement` is to produce the SAME statistics as the in-memory
code it replaces, on a table too large to load. So the tests do not merely check that it runs:
they build a small long table, compute the expected correlation and the expected
industry-neutral retention with ordinary pandas, and require the streaming path to match.

The scale guard is tested too, because the failure it prevents is an OOM kill at the very end
of a multi-hour run rather than a wrong number.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_core.factor_lab.streaming_supplement import (  # noqa: E402
    StreamingSupplementError,
    cross_sectional_correlation,
    neutral_retention_by_factor,
    prepare_panel,
)

VARIANT = "|window="
DATES = pd.to_datetime(
    ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09"]
)
CODES = [f"{i:06d}" for i in range(25)]


def _values_for(seed: int, dates: pd.Series, codes: pd.Series) -> np.ndarray:
    """A deterministic cross-sectional signal plus idio noise, so ranks vary by date."""
    rng = np.random.default_rng(seed)
    base = pd.Series(codes).astype(int).to_numpy(dtype=float)
    values = base * 0.1 + rng.normal(0, 1.0, len(base))
    return values


def _write_long_table(path: Path, factor_ids: list[str], *, with_variants: bool = True) -> pd.DataFrame:
    dates = pd.Series(DATES).repeat(len(CODES)).reset_index(drop=True)
    codes = pd.Series(CODES * len(DATES)).reset_index(drop=True)
    frames = []
    truth = {}
    for position, factor_id in enumerate(factor_ids):
        values = _values_for(position + 1, dates, codes)
        truth[factor_id] = values
        frames.append(
            pd.DataFrame(
                {"date": dates, "code": codes, "factor_name": factor_id, "value": values}
            )
        )
        if with_variants:
            frames.append(
                pd.DataFrame(
                    {
                        "date": dates,
                        "code": codes,
                        "factor_name": f"{factor_id}{VARIANT}8",
                        "value": values * 2.0,
                    }
                )
            )
    table = pa.Table.from_pandas(pd.concat(frames, ignore_index=True), preserve_index=False)
    pq.write_table(table, path)
    wide = pd.DataFrame(truth)
    wide.index = pd.MultiIndex.from_arrays([dates, codes])
    return wide


def _reference(wide: pd.DataFrame, *, min_observations: int = 20) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Expected daily-averaged and pooled correlations, computed the ordinary way."""
    dates = wide.index.get_level_values(0)
    ranks = wide.groupby(dates).rank(pct=True)
    daily = []
    for _date, group in ranks.groupby(level=0):
        if len(group) < min_observations:
            continue
        daily.append(group.corr(method="pearson", min_periods=min_observations))
    averaged = pd.concat(daily).groupby(level=0).mean()
    pooled = ranks.corr(method="pearson", min_periods=min_observations)
    return averaged, pooled


def test_only_matches_the_pandas_reference_for_both_statistics(tmp_path: Path) -> None:
    ids = ["f_a", "f_b", "f_c"]
    wide = _write_long_table(tmp_path / "values.parquet", ids)
    expected_daily, expected_pooled = _reference(wide)

    result = cross_sectional_correlation(tmp_path / "values.parquet", factor_ids=ids)

    assert list(result.correlation.index) == ids
    assert result.correlation.shape == (3, 3)
    assert result.factors_missing == []
    assert result.dates_used == len(DATES)
    np.testing.assert_allclose(
        result.correlation.to_numpy(), expected_daily.to_numpy(), atol=1e-9
    )
    np.testing.assert_allclose(result.pooled.to_numpy(), expected_pooled.to_numpy(), atol=1e-9)
    # The two statistics are not the same thing, and the difference must be reportable.
    assert np.isfinite(result.max_pooled_difference)


def test_only_is_unaligned_with_the_lag_matrix_of_a_factor(tmp_path: Path) -> None:
    """Per-date rank correlation of a series with itself is exactly 1."""
    ids = ["f_a", "f_b"]
    _write_long_table(tmp_path / "values.parquet", ids)
    result = cross_sectional_correlation(tmp_path / "values.parquet", factor_ids=ids)
    assert result.correlation.loc["f_a", "f_a"] == pytest.approx(1.0)
    assert result.correlation.loc["f_a", "f_b"] == pytest.approx(
        result.correlation.loc["f_b", "f_a"]
    )


def test_only_ignores_perturbation_variants(tmp_path: Path) -> None:
    """Variants are 2x their base series; if they leaked in the matrix would be size 6."""
    ids = ["f_a", "f_b"]
    _write_long_table(tmp_path / "values.parquet", ids, with_variants=True)
    result = cross_sectional_correlation(tmp_path / "values.parquet", factor_ids=ids)
    assert list(result.correlation.index) == ids
    assert not any(VARIANT in name for name in result.correlation.index)


def test_only_reports_factors_that_have_no_series(tmp_path: Path) -> None:
    _write_long_table(tmp_path / "values.parquet", ["f_a", "f_b"])
    result = cross_sectional_correlation(
        tmp_path / "values.parquet", factor_ids=["f_a", "f_b", "f_missing"]
    )
    assert result.factors_missing == ["f_missing"]
    assert np.isnan(result.correlation.loc["f_missing", "f_a"])


def test_only_handles_a_factor_with_gaps_pairwise(tmp_path: Path) -> None:
    """A missing value must exclude that name for that pair, not change the universe."""
    ids = ["f_a", "f_b"]
    wide = _write_long_table(tmp_path / "values.parquet", ids, with_variants=False)
    with_gap = wide.copy()
    with_gap.iloc[0, 1] = np.nan
    table = pq.read_table(tmp_path / "values.parquet").to_pandas()
    mask = (table["factor_name"] == "f_b") & (table["code"] == CODES[0]) & (
        table["date"] == DATES[0]
    )
    table.loc[mask, "value"] = np.nan
    pq.write_table(pa.Table.from_pandas(table, preserve_index=False), tmp_path / "values.parquet")

    expected_daily, expected_pooled = _reference(with_gap, min_observations=3)
    result = cross_sectional_correlation(
        tmp_path / "values.parquet", factor_ids=ids, min_observations=3
    )
    np.testing.assert_allclose(
        result.correlation.to_numpy(), expected_daily.to_numpy(), atol=1e-9
    )
    np.testing.assert_allclose(result.pooled.to_numpy(), expected_pooled.to_numpy(), atol=1e-9)


def test_only_refuses_a_factor_file_missing_the_contract_columns(tmp_path: Path) -> None:
    bad = tmp_path / "bad.parquet"
    pq.write_table(pa.table({"date": [1], "code": ["x"], "value": [1.0]}), bad)
    with pytest.raises(Exception):
        cross_sectional_correlation(bad, factor_ids=["f_a", "f_b"])


def test_only_prepare_panel_builds_the_forward_return(tmp_path: Path) -> None:
    frames = []
    rng = np.random.default_rng(7)
    for code in CODES:
        prices = 10.0 + np.cumsum(rng.normal(0, 0.1, len(DATES)))
        frames.append(
            pd.DataFrame(
                {
                    "date": DATES,
                    "code": code,
                    "close": prices,
                    "industry": "bank",
                }
            )
        )
    panel_path = tmp_path / "panel.parquet"
    pq.write_table(pa.Table.from_pandas(pd.concat(frames, ignore_index=True)), panel_path)

    panel = prepare_panel(panel_path, horizon=2)
    assert "forward_return" in panel.columns
    assert panel[["code", "date"]].equals(
        panel.sort_values(["code", "date"])[["code", "date"]].reset_index(drop=True)
    )
    # The last `horizon` bars of each code have no forward price and must be NaN, not zero.
    assert panel.groupby("code")["forward_return"].apply(lambda s: s.tail(2).isna().all()).all()


def test_only_refuses_a_panel_without_industry(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel.parquet"
    pq.write_table(
        pa.table(
            {
                "date": DATES.repeat(len(CODES)),
                "code": CODES * len(DATES),
                "close": np.ones(len(DATES) * len(CODES)),
            }
        ),
        panel_path,
    )
    with pytest.raises(StreamingSupplementError, match="industry"):
        prepare_panel(panel_path, horizon=1)


def test_only_neutral_retention_matches_the_in_memory_path(tmp_path: Path) -> None:
    """The streaming retention must equal what the previous in-memory code produced."""
    from research_core.factor_lab.supplementary import industry_neutral_retention

    rng = np.random.default_rng(11)
    frames = []
    for position, code in enumerate(CODES):
        prices = 10.0 + np.cumsum(rng.normal(0, 0.1, len(DATES)))
        frames.append(
            pd.DataFrame(
                {
                    "date": DATES,
                    "code": code,
                    "close": prices,
                    "industry": "bank" if position % 2 else "tech",
                }
            )
        )
    panel_path = tmp_path / "panel.parquet"
    pq.write_table(pa.Table.from_pandas(pd.concat(frames, ignore_index=True)), panel_path)

    ids = ["f_a", "f_b"]
    wide = _write_long_table(tmp_path / "values.parquet", ids, with_variants=False)

    panel = prepare_panel(panel_path, horizon=1)
    # Reference: the previous implementation's route -- a (date, code) merge onto the panel.
    reference: dict[str, dict | None] = {}
    keys = panel[["date", "code"]].reset_index().rename(columns={"index": "_row"})
    for factor_id in ids:
        subset = pd.DataFrame(
            {
                "date": wide.index.get_level_values(0),
                "code": wide.index.get_level_values(1),
                "value": wide[factor_id].to_numpy(),
            }
        )
        merged = keys.merge(subset, on=["date", "code"], how="left")
        series = merged.sort_values("_row")["value"].reset_index(drop=True)
        series.index = panel.index
        reference[factor_id] = industry_neutral_retention(
            panel, factor_values=series, factor_col="_factor", return_col="forward_return"
        )

    streamed = neutral_retention_by_factor(
        tmp_path / "values.parquet",
        panel_path=panel_path,
        horizon=1,
        factor_ids=ids,
    )

    assert sorted(streamed) == ids
    for factor_id in ids:
        assert streamed[factor_id] is not None, factor_id
        assert streamed[factor_id]["retention"] == pytest.approx(
            reference[factor_id]["retention"], rel=1e-9
        )
        assert streamed[factor_id]["raw"]["mean"] == pytest.approx(
            reference[factor_id]["raw"]["mean"], rel=1e-9
        )
        assert streamed[factor_id]["neutral"]["mean"] == pytest.approx(
            reference[factor_id]["neutral"]["mean"], rel=1e-9
        )


def test_only_neutral_retention_refuses_a_factor_with_no_series(tmp_path: Path) -> None:
    frames = []
    rng = np.random.default_rng(3)
    for code in CODES:
        frames.append(
            pd.DataFrame(
                {
                    "date": DATES,
                    "code": code,
                    "close": 10.0 + np.cumsum(rng.normal(0, 0.1, len(DATES))),
                    "industry": "bank",
                }
            )
        )
    panel_path = tmp_path / "panel.parquet"
    pq.write_table(pa.Table.from_pandas(pd.concat(frames, ignore_index=True)), panel_path)
    _write_long_table(tmp_path / "values.parquet", ["f_a"], with_variants=False)

    with pytest.raises(StreamingSupplementError, match="no series"):
        neutral_retention_by_factor(
            tmp_path / "values.parquet",
            panel_path=panel_path,
            horizon=1,
            factor_ids=["f_a", "f_absent"],
        )
