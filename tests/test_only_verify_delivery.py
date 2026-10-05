"""TEST-ONLY tests for the final delivery acceptance check.

The hand-off is automatic now, so acceptance can arrive without preparation. These tests pin
the properties that make the check worth trusting: it must fail loudly on the things that would
make a delivery wrong, and it must not invent a pass on an empty directory.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from research_core.factor_lab.delivery_manifest import DELIVERY_MANIFEST_COLUMNS  # noqa: E402
from verify_delivery import verify  # noqa: E402


def _write_manifest(delivery: Path, rows: list[dict]) -> None:
    delivery.mkdir(parents=True, exist_ok=True)
    with (delivery / "delivery_manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(DELIVERY_MANIFEST_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in DELIVERY_MANIFEST_COLUMNS})


def _delivered(factor_id: str) -> dict:
    return {
        "factor_id": factor_id, "status": "validated", "in_delivery_package": "true",
        "fdr_accepted": "true", "industry_neutral_retention": "0.62",
        "risk_exposure": "false", "failed_gates": "",
    }


def _complete_delivery(root: Path, delivered: int = 305) -> Path:
    delivery = root / "delivery"
    rows = [_delivered(f"F{i:03d}") for i in range(delivered)]
    rows += [{"factor_id": "BAD", "status": "rejected", "in_delivery_package": "false",
              "failed_gates": "residual_ic"}]
    _write_manifest(delivery, rows)

    (delivery / "supplementary_report.json").write_text(
        json.dumps({"summary": {"q": 0.05, "n_tested": 306, "n_accepted": delivered}}),
        encoding="utf-8",
    )
    demos = delivery / "strategy_demos"
    demos.mkdir(parents=True, exist_ok=True)
    (demos / "backtest_results.json").write_text(
        json.dumps({
            "backtest_window": {"start": "2023-09-28", "end": "2026-08-31"},
            "results": {"delivery_cluster_core_v1": {"metrics": {"total_return": 0.1179}}},
        }),
        encoding="utf-8",
    )
    (demos / "clusters.json").write_text(
        json.dumps({"representatives": ["F001"], "n_clusters": 1}), encoding="utf-8"
    )
    signals = delivery / "live_signals"
    signals.mkdir(parents=True, exist_ok=True)
    (signals / "file_orders.csv").write_bytes(
        "\ufeffcode,side,shares\n600000.XSHG,buy,100\n".encode("utf-8")
    )
    (signals / "conditional_orders.json").write_text(json.dumps([{"code": "600000.XSHG"}]),
                                                     encoding="utf-8")
    (signals / "supabase_rows.json").write_text(
        json.dumps([{"code": "600000.XSHG", "pushed": False}]), encoding="utf-8"
    )
    (signals / "signal_summary.json").write_text(json.dumps({"trade_date": "2026-08-31"}),
                                                 encoding="utf-8")

    package = delivery / "package"
    (package / "factors").mkdir(parents=True, exist_ok=True)
    for index in range(delivered):
        (package / "factors" / f"F{index:03d}").mkdir(exist_ok=True)
    (package / "package_manifest.json").write_text(
        json.dumps({"counts": {"included": delivered, "excluded": 1}}), encoding="utf-8"
    )
    (delivery / "cross_check.json").write_text(json.dumps({"finding_count": 0}), encoding="utf-8")
    (delivery / "README.md").write_text(
        f"## 一、交付了什么\n- 达成 300 的目标：**{'是' if delivered >= 300 else '否'}**\n",
        encoding="utf-8",
    )
    return delivery


def test_only_an_empty_directory_fails_rather_than_passing_quietly(tmp_path: Path) -> None:
    delivery = tmp_path / "empty"
    delivery.mkdir()
    check = verify(delivery)
    assert check.failed, "an empty delivery must not pass"
    assert any("missing" in detail for _, _, detail in check.failed)


def test_only_a_complete_delivery_passes_every_check(tmp_path: Path) -> None:
    check = verify(_complete_delivery(tmp_path, delivered=305))
    assert not check.failed, check.report()


def test_only_a_short_delivery_fails_the_count_check(tmp_path: Path) -> None:
    check = verify(_complete_delivery(tmp_path, delivered=299))
    assert any("delivered count" in name for _, name, _ in check.failed), check.report()


def test_only_a_slipped_through_rejected_factor_is_caught(tmp_path: Path) -> None:
    """The one thing the package must never contain."""
    delivery = _complete_delivery(tmp_path, delivered=305)
    with (delivery / "delivery_manifest.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["status"] = "rejected"          # still flagged as in the package
    _write_manifest(delivery, rows)

    check = verify(delivery)
    assert any("only validated" in name for _, name, _ in check.failed), check.report()


def test_only_a_fdr_disagreement_between_report_and_manifest_is_caught(tmp_path: Path) -> None:
    delivery = _complete_delivery(tmp_path, delivered=305)
    (delivery / "supplementary_report.json").write_text(
        json.dumps({"summary": {"q": 0.05, "n_tested": 306, "n_accepted": 12}}),
        encoding="utf-8",
    )
    check = verify(delivery)
    assert any("fdr_accepted agrees" in name for _, name, _ in check.failed), check.report()


def test_only_a_cross_check_finding_is_caught(tmp_path: Path) -> None:
    delivery = _complete_delivery(tmp_path, delivered=305)
    (delivery / "cross_check.json").write_text(json.dumps({"finding_count": 3}), encoding="utf-8")
    check = verify(delivery)
    assert any("cross-check" in name for _, name, _ in check.failed), check.report()


def test_only_a_readme_that_lies_about_the_count_is_caught(tmp_path: Path) -> None:
    delivery = _complete_delivery(tmp_path, delivered=305)
    (delivery / "README.md").write_text("## 一、交付了什么\n- 达成 300 的目标：**否**\n",
                                        encoding="utf-8")
    check = verify(delivery)
    assert any("README states the target" in name for _, name, _ in check.failed), check.report()


def test_only_rows_claiming_a_supabase_push_are_caught(tmp_path: Path) -> None:
    """The repo has no Supabase client, so a pushed:true row would be a false claim."""
    delivery = _complete_delivery(tmp_path, delivered=305)
    (delivery / "live_signals" / "supabase_rows.json").write_text(
        json.dumps([{"code": "600000.XSHG", "pushed": True}]), encoding="utf-8"
    )
    check = verify(delivery)
    assert any("pushed" in name for _, name, _ in check.failed), check.report()


def test_only_file_orders_must_carry_the_bom(tmp_path: Path) -> None:
    delivery = _complete_delivery(tmp_path, delivered=305)
    (delivery / "live_signals" / "file_orders.csv").write_bytes(
        "code,side,shares\n600000.XSHG,buy,100\n".encode("utf-8")
    )
    check = verify(delivery)
    assert any("BOM" in name for _, name, _ in check.failed), check.report()
