"""TEST-ONLY tests for the generated delivery README.

The delivery produces a lot of artifacts and no page saying which is which. A hand-written one
would carry numbers that go stale the moment the chain re-runs, so it is generated from the
artifacts -- and the two things that must never be wrong are the delivered count and the
honesty about it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_delivery_readme import ReadmeError, build_readme, main  # noqa: E402


def _delivery(root: Path, **files) -> Path:
    """Write artifact JSONs.

    Each key is the file's path relative to the delivery directory without the ``.json``
    suffix, so ``delivery_manifest.summary`` and ``strategy_demos/backtest_results`` both name
    real artifact paths rather than a flattened stand-in.
    """
    root.mkdir(parents=True, exist_ok=True)
    for name, payload in files.items():
        target = root / f"{name}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload), encoding="utf-8")
    return root


def _manifest(count: int) -> dict:
    return {
        "total": 849,
        "validated": count,
        "rejected": 100,
        "not_run": 849 - count - 100,
        "in_delivery_package": count,
        "in_delivery_package_tier_sa": max(0, count - 90),
        "delivered_clusters": 40,
        "representatives": 40,
    }


def test_only_states_the_count_and_that_the_target_was_met(tmp_path: Path) -> None:
    delivery = _delivery(tmp_path / "d", **{"delivery_manifest.summary": _manifest(312)})
    text = build_readme(delivery)
    assert "312" in text
    assert "达成 300 的目标：**是**" in text
    assert "没有放宽任何冻结门槛" not in text, "no warning is needed when the target is met"


def test_only_says_so_when_the_target_is_missed(tmp_path: Path) -> None:
    delivery = _delivery(tmp_path / "d", **{"delivery_manifest.summary": _manifest(244)})
    text = build_readme(delivery)
    assert "达成 300 的目标：**否**" in text
    assert "没有放宽任何冻结门槛" in text


def test_only_names_the_artifacts_that_do_not_exist_rather_than_omitting_them(
    tmp_path: Path,
) -> None:
    delivery = _delivery(tmp_path / "d", **{"delivery_manifest.summary": _manifest(3)})
    text = build_readme(delivery)
    # Missing layers are stated, not silently dropped.
    assert "尚未生成策略演示" in text
    assert "本次未生成实盘信号" in text
    # The artifact list is always present, so a reader can see what should exist.
    assert "delivery_manifest.csv" in text
    # The reconciliation tool is documented regardless of whether this run produced signals:
    # it is used against the client's own fills, days later.
    assert "reconcile_signals.py" in text
    assert "deviation_report" in text


def test_only_reports_the_signal_summary_and_never_claims_a_push(tmp_path: Path) -> None:
    delivery = _delivery(
        tmp_path / "d",
        **{
            "delivery_manifest.summary": _manifest(3),
            "live_signals/signal_summary": {
                "strategy_id": "chenxi_core_v1", "trade_date": "2026-08-31",
                "n_targets": 50, "n_orders": 50, "n_buys": 50, "n_sells": 0,
                "core_factors": ["ALPHA360:HIGH36"],
            },
        },
    )
    text = build_readme(delivery)
    assert "2026-08-31" in text
    assert "ALPHA360:HIGH36" in text
    assert "pushed: false" in text, "the README must not claim a Supabase push happened"


def test_only_includes_the_out_of_sample_table_with_negative_numbers_intact(
    tmp_path: Path,
) -> None:
    delivery = _delivery(
        tmp_path / "d",
        **{
            "delivery_manifest.summary": _manifest(3),
            "strategy_demos/backtest_results": {
                "backtest_window": {"start": "2023-09-28", "end": "2026-08-31"},
                "cost_model": {"round_trip_total": 0.003},
                "results": {
                    "delivery_cluster_core_v1": {
                        "metrics": {
                            "total_return": 0.1179, "annualized_return": 0.0406,
                            "benchmark_return": 0.4242, "excess_return": -0.3063,
                            "max_drawdown": 0.5279,
                        }
                    }
                },
            },
        },
    )
    text = build_readme(delivery)
    assert "2023-09-28" in text
    assert "11.79%" in text
    assert "-30.63%" in text, "a negative excess return must be shown as negative"
    assert "未做任何收益承诺" in text


def test_only_reports_the_cross_check_and_package_counts(tmp_path: Path) -> None:
    delivery = _delivery(
        tmp_path / "d",
        **{
            "delivery_manifest.summary": _manifest(3),
            "cross_check": {"finding_count": 0},
            "package/package_manifest": {"counts": {"included": 69, "excluded": 55}},
        },
    )
    text = build_readme(delivery)
    assert "发现数 0" in text
    assert "入选 69" in text
    assert "排除 55" in text


def test_only_refuses_a_delivery_directory_that_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(ReadmeError, match="not found"):
        main(["--delivery-dir", str(tmp_path / "nope")])
