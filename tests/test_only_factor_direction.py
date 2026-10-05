"""TEST-ONLY tests for trading direction.

The delivery's live signals and strategy demos are long-only: they buy the TOP of the
composite score. A factor whose training-segment IC is negative predicts a LOW return when its
value is high, so unless its rank is inverted first, every reverse-signalled factor is traded
on the wrong side -- and roughly half of the delivered factors are reverse-signalled (10 of the
first 18). The first full rehearsal measured the consequence: a -0.58 excess return, with all
four demo variants losing money.

`training.direction` comes from the frozen validator and is measured on the training split
only, so orienting by it leaks nothing into an out-of-sample backtest. These tests pin the
orientation arithmetic and the refusal to trade a factor whose sign is unknown.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))


from research_core.factor_lab.streaming_supplement import (  # noqa: E402
    composite_scores,
    ranked_block,
    unoriented_factors,
)

DATES = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
CODES = [f"{600000 + i}" for i in range(20)]


def _write_table(
    path: Path,
    factor_ids: list[str],
    *,
    dates: pd.Series | None = None,
    codes: list[str] | None = None,
) -> None:
    dates = pd.Series(DATES) if dates is None else pd.Series(dates)
    codes = CODES if codes is None else codes
    dates = dates.repeat(len(codes)).reset_index(drop=True)
    codes = pd.Series(codes * (len(dates) // len(codes))).reset_index(drop=True)
    frames = []
    for position, factor_id in enumerate(factor_ids):
        rng = np.random.default_rng(position + 1)
        values = pd.Series(codes).astype(int).to_numpy() * 0.1 + rng.normal(0, 1.0, len(codes))
        frames.append(
            pd.DataFrame(
                {"date": dates, "code": codes, "factor_name": factor_id, "value": values}
            )
        )
    pq.write_table(
        pa.Table.from_pandas(pd.concat(frames, ignore_index=True), preserve_index=False), path
    )


def test_only_flipping_direction_mirrors_the_score_about_one_half(tmp_path: Path) -> None:
    _write_table(tmp_path / "v.parquet", ["f_a"])
    block = ranked_block(tmp_path / "v.parquet", factor_ids=["f_a"])

    forward = composite_scores(block, None, columns=["f_a"], directions={"f_a": 1.0})
    reverse = composite_scores(block, None, columns=["f_a"], directions={"f_a": -1.0})
    merged = forward.merge(reverse, on=["date", "code"], suffixes=("_f", "_r"))

    assert len(merged) == len(forward)
    np.testing.assert_allclose(
        merged["score_f"].to_numpy() + merged["score_r"].to_numpy(), 1.0, atol=1e-6
    )
    # A factor that is not flipped is a different strategy, not a relabelled one.
    assert not np.allclose(merged["score_f"], merged["score_r"])


def test_only_orientation_is_applied_per_factor_not_globally(tmp_path: Path) -> None:
    """A mixed-sign basket must orient each leg, not flip the whole basket."""
    _write_table(tmp_path / "v.parquet", ["pos", "neg"])
    block = ranked_block(tmp_path / "v.parquet", factor_ids=["pos", "neg"])

    aligned = composite_scores(
        block, None, columns=["pos", "neg"], directions={"pos": 1.0, "neg": -1.0}
    )
    naive = composite_scores(block, None, columns=["pos", "neg"], directions={"pos": 1.0, "neg": 1.0})
    merged = aligned.merge(naive, on=["date", "code"], suffixes=("_a", "_n"))

    assert not np.allclose(merged["score_a"], merged["score_n"])
    # With the second leg correctly inverted, the aligned basket is not simply the mirror of
    # the naive one: it sits between the two legs' orientations.
    per_leg_pos = composite_scores(block, None, columns=["pos"], directions={"pos": 1.0})
    per_leg_neg = composite_scores(block, None, columns=["neg"], directions={"neg": -1.0})
    both = per_leg_pos.merge(per_leg_neg, on=["date", "code"], suffixes=("_p", "_n"))
    expected = (both["score_p"].to_numpy() + both["score_n"].to_numpy()) / 2.0
    np.testing.assert_allclose(merged["score_a"].to_numpy(), expected, atol=1e-6)


def test_only_unoriented_factors_reports_every_unknown_sign() -> None:
    assert unoriented_factors(["a", "b"], {"a": 1.0}) == ["b"]
    assert unoriented_factors(["a", "b"], {}) == ["a", "b"]
    assert unoriented_factors(["a", "b"], None) == ["a", "b"]
    assert unoriented_factors(["a"], {"a": -1.0}) == []


def _write_demo_inputs(root: Path, *, with_direction: bool) -> dict:
    """Self-contained fixture.

    Deliberately not shared with `test_only_strategy_demos`: that fixture is edited by other
    work in this repository, and a sign check that breaks whenever someone changes an unrelated
    fixture signature is a check nobody will trust.
    """
    import json

    codes = CODES[:12]
    # The demo rebalances on month-ends, so the fixture needs a calendar that contains some.
    calendar = pd.bdate_range("2020-01-02", periods=70)
    frame = pd.DataFrame(
        {
            "date": list(calendar) * len(codes),
            "code": [code for code in codes for _ in calendar],
            "close": [
                10.0 + position + (index % 7) * 0.05
                for position, code in enumerate(codes)
                for index in range(len(calendar))
            ],
            "industry": "bank",
        }
    )
    panel = root / "panel.parquet"
    pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), panel)
    (root / "panel.parquet.json").write_text(json.dumps({"source": "RQData FULL"}), encoding="utf-8")

    _write_table(root / "values.parquet", ["d_a"], dates=calendar, codes=codes)
    (root / "values.parquet.json").write_text(json.dumps({"source": "real"}), encoding="utf-8")

    target = root / "runs" / "d_a"
    target.mkdir(parents=True, exist_ok=True)
    training = {"primary_rank_ic_mean": 0.02}
    if with_direction:
        training["direction"] = 1.0
    (target / "validation_result.json").write_text(
        json.dumps(
            {
                "factor_id": "d_a",
                "status": "validated",
                "failed_gates": [],
                "result_hash": "a" * 64,
                "rank_ic": {"10d": {"mean": 0.03, "ic_ir": 0.4, "t_stat": 3.5, "yearly": {}}},
                "training": training,
            }
        ),
        encoding="utf-8",
    )
    return {"panel": panel, "factors": root / "values.parquet", "runs": root / "runs"}


def test_only_demo_refuses_a_factor_with_no_training_direction(tmp_path: Path) -> None:
    """An unknown sign must stop the run, not be silently treated as positive."""
    import build_strategy_demos  # noqa: PLC0415


    inputs = _write_demo_inputs(tmp_path, with_direction=False)
    argv = [
        "--panel-file", str(inputs["panel"]),
        "--factor-file", str(inputs["factors"]),
        "--runs-dir", str(inputs["runs"]),
        "--out-dir", str(tmp_path / "out"),
    ]
    try:
        build_strategy_demos.main(argv)
    except SystemExit as exc:
        assert "training direction" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("the demo traded a factor whose sign is unknown")


def test_only_demo_trades_when_every_factor_carries_a_direction(tmp_path: Path) -> None:
    """The guard must not fire when the direction is present -- it is a check, not a wall."""
    import build_strategy_demos  # noqa: PLC0415


    inputs = _write_demo_inputs(tmp_path, with_direction=True)
    argv = [
        "--panel-file", str(inputs["panel"]),
        "--factor-file", str(inputs["factors"]),
        "--runs-dir", str(inputs["runs"]),
        "--out-dir", str(tmp_path / "out"),
    ]
    assert build_strategy_demos.main(argv) == 0
    assert (tmp_path / "out" / "strategies.json").is_file()

