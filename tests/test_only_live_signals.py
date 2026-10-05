"""TEST-ONLY tests for the live-signal producer.

The signal stage had no entry point at all before this script: `signal_pipeline` is a library
with no `__main__` and nothing in the repository called it. These tests pin what the client
actually receives -- a QMT-importable 文件单, a 条件单 file with trigger prices, and Supabase
rows in the target shape -- and pin the honesty guard that matters most: if the delivered core
set has no factor values, the script must refuse rather than trade a different set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_live_signals import LiveSignalError, main  # noqa: E402

DATES = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
CODES = [f"{600000 + i}" for i in range(12)]
CORE = ["alpha_a", "alpha_b"]
MANIFEST_COLUMNS = [
    "factor_id", "in_delivery_package", "cluster_role", "composite", "tier",
]


def _write_inputs(root: Path, *, with_core_values: bool = True) -> dict:
    frames = []
    rng = np.random.default_rng(5)
    for position, code in enumerate(CODES):
        frames.append(
            pd.DataFrame(
                {
                    "date": DATES,
                    "code": code,
                    "close": 10.0 + position + np.arange(len(DATES)) * 0.1,
                }
            )
        )
    panel_path = root / "panel.parquet"
    pq.write_table(pa.Table.from_pandas(pd.concat(frames, ignore_index=True)), panel_path)

    dates = pd.Series(DATES).repeat(len(CODES)).reset_index(drop=True)
    codes = pd.Series(CODES * len(DATES)).reset_index(drop=True)
    series = []
    for position, factor_id in enumerate(CORE if with_core_values else ["other_factor"]):
        values = rng.normal(size=len(codes)) + pd.Series(codes).astype(int).to_numpy() * 0.001
        series.append(
            pd.DataFrame(
                {"date": dates, "code": codes, "factor_name": factor_id, "value": values}
            )
        )
    factor_path = root / "values.parquet"
    pq.write_table(pa.Table.from_pandas(pd.concat(series, ignore_index=True)), factor_path)

    runs = root / "runs"
    for factor_id in CORE:
        target = runs / factor_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "validation_result.json").write_text(
            json.dumps(
                {
                    "factor_id": factor_id,
                    "status": "validated",
                    "failed_gates": [],
                    "result_hash": "a" * 64,
                    "rank_ic": {"10d": {"mean": 0.04, "ic_ir": 0.3, "t_stat": 3.0, "yearly": {}}},
                }
            ),
            encoding="utf-8",
        )

    manifest = root / "delivery_manifest.csv"
    pd.DataFrame(
        [
            {"factor_id": "alpha_a", "in_delivery_package": "true",
             "cluster_role": "representative", "composite": "70.0", "tier": "A"},
            {"factor_id": "alpha_b", "in_delivery_package": "true",
             "cluster_role": "member", "composite": "60.0", "tier": "B"},
            {"factor_id": "alpha_c", "in_delivery_package": "false",
             "cluster_role": "member", "composite": "30.0", "tier": "C"},
        ],
        columns=MANIFEST_COLUMNS,
    ).to_csv(manifest, index=False, encoding="utf-8-sig")

    return {"panel": panel_path, "factors": factor_path, "runs": runs, "manifest": manifest}


def _args(inputs: dict, out_dir: Path, **overrides) -> list[str]:
    values = {
        "--panel-file": str(inputs["panel"]),
        "--factor-file": str(inputs["factors"]),
        "--runs-dir": str(inputs["runs"]),
        "--delivery-manifest": str(inputs["manifest"]),
        "--out-dir": str(out_dir),
        "--top-n": "5",
        "--total-value": "1000000",
    }
    values.update({key: str(value) for key, value in overrides.items()})
    argv: list[str] = []
    for key, value in values.items():
        argv += [key, value]
    return argv


def test_only_writes_all_three_signal_artifacts(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    out_dir = tmp_path / "out"
    assert main(_args(inputs, out_dir)) == 0

    csv_path = out_dir / "file_orders.csv"
    conditional = out_dir / "conditional_orders.json"
    rows_path = out_dir / "supabase_rows.json"
    assert csv_path.is_file() and conditional.is_file() and rows_path.is_file()

    # A QMT 文件单 is read by Excel/QMT, so the BOM has to be there.
    assert csv_path.read_bytes()[:3] == b"\xef\xbb\xbf"
    orders = pd.read_csv(csv_path, encoding="utf-8-sig")
    assert list(orders.columns) == [
        "code", "side", "shares", "price_type", "reference_price", "target_weight", "reason",
    ]
    assert len(orders) > 0
    assert set(orders["side"]) <= {"buy", "sell"}

    payload = json.loads(conditional.read_text(encoding="utf-8"))
    assert payload["strategy_id"] == "chenxi_core_v1"
    assert payload["trade_date"] == "2020-01-06"
    assert len(payload["orders"]) == len(orders)
    for order in payload["orders"]:
        assert order["price_type"] == "limit"
        assert order["trigger_price"] > 0

    rows = json.loads(rows_path.read_text(encoding="utf-8"))
    assert rows["pushed"] is False, "the rows must not claim to have been uploaded"
    assert rows["upsert_key"] == ["strategy_id", "trade_date", "code"]
    assert len(rows["rows"]) == len(orders)
    assert all(row["status"] == "pending" for row in rows["rows"])

    summary = json.loads((out_dir / "signal_summary.json").read_text(encoding="utf-8"))
    # Only the representative is traded, not the whole delivered set.
    assert summary["core_factors"] == ["alpha_a"]
    assert summary["n_orders"] == len(orders)


def test_only_trades_the_whole_delivered_set_when_there_is_no_representative(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    frame = pd.read_csv(inputs["manifest"], dtype=str, encoding="utf-8-sig")
    frame["cluster_role"] = "member"
    frame.to_csv(inputs["manifest"], index=False, encoding="utf-8-sig")

    out_dir = tmp_path / "out"
    assert main(_args(inputs, out_dir)) == 0
    summary = json.loads((out_dir / "signal_summary.json").read_text(encoding="utf-8"))
    assert summary["core_factors"] == ["alpha_a", "alpha_b"]


def test_only_refuses_when_the_core_set_has_no_factor_values(tmp_path: Path) -> None:
    """Trading a different set than the one delivered would misstate the signals."""
    inputs = _write_inputs(tmp_path, with_core_values=False)
    with pytest.raises(LiveSignalError, match="no factor values"):
        main(_args(inputs, tmp_path / "out"))


def test_only_refuses_an_empty_package(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    frame = pd.read_csv(inputs["manifest"], dtype=str, encoding="utf-8-sig")
    frame["in_delivery_package"] = "false"
    frame.to_csv(inputs["manifest"], index=False, encoding="utf-8-sig")

    with pytest.raises(LiveSignalError, match="nothing to trade"):
        main(_args(inputs, tmp_path / "out"))


def test_only_emits_no_orders_when_the_book_already_matches(tmp_path: Path) -> None:
    inputs = _write_inputs(tmp_path)
    out_dir = tmp_path / "out"
    assert main(_args(inputs, out_dir)) == 0
    orders = pd.read_csv(out_dir / "file_orders.csv", encoding="utf-8-sig")

    holdings = {
        str(code): int(shares) for code, shares in zip(orders["code"], orders["shares"])
    }
    holdings_path = tmp_path / "holdings.json"
    holdings_path.write_text(json.dumps(holdings), encoding="utf-8")

    second = tmp_path / "out2"
    assert main(_args(inputs, second, **{"--holdings": holdings_path})) == 0
    assert not (second / "file_orders.csv").exists()
