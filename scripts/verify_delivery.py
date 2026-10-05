"""Final acceptance check on a delivery directory.

Read-only: this inspects what was produced and prints a verdict. It exists because the hand-off
is now automatic, so the moment of acceptance could arrive without me having prepared for it --
and re-deriving "is this delivery complete and self-consistent" from memory at that point is
exactly how a shortfall gets reported as a success.

Every check states what it looked for and what it found, so a failure is specific. Exit code 0
means every check passed.

    python -X utf8 scripts/verify_delivery.py --delivery-dir delivery
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The column contract is imported, never restated. A local copy would drift from the library
# exactly the way this project's other duplicated constants did, and the check would then be
# verifying a stale contract against a stale contract.
from research_core.factor_lab.delivery_manifest import (  # noqa: E402
    DELIVERY_MANIFEST_COLUMNS as MANIFEST_COLUMNS,
)

#: The delivery commitment.
TARGET = 300


class Check:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str, str]] = []

    def add(self, ok: bool, name: str, detail: str) -> None:
        self.rows.append((bool(ok), name, detail))

    @property
    def failed(self) -> list[tuple[bool, str, str]]:
        return [row for row in self.rows if not row[0]]

    def report(self) -> str:
        lines = []
        for ok, name, detail in self.rows:
            lines.append(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        return "\n".join(lines)


def load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def verify(delivery: Path, *, target: int = TARGET) -> Check:
    check = Check()

    # ── the manifest: the authoritative table ────────────────────────
    manifest = delivery / "delivery_manifest.csv"
    if not manifest.is_file():
        check.add(False, "delivery_manifest.csv", "missing")
        return check
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        rows = list(reader)
    check.add(
        tuple(columns) == MANIFEST_COLUMNS,
        "manifest columns",
        f"{len(columns)} columns, frozen order {'matches' if tuple(columns) == MANIFEST_COLUMNS else 'DIFFERS'}"
        + ("" if tuple(columns) == MANIFEST_COLUMNS else f" -- got {columns}"),
    )
    delivered = [row for row in rows if str(row.get("in_delivery_package")) == "true"]
    check.add(
        len(delivered) >= target,
        "delivered count",
        f"{len(delivered)} in the package (target {target})",
    )
    # Everything shipped must have passed the frozen gates.
    not_passed = [r["factor_id"] for r in delivered if r.get("status") != "validated"]
    check.add(not not_passed, "package contains only validated factors",
              f"{len(not_passed)} offenders" + (f": {not_passed[:5]}" if not_passed else ""))
    exposed = [r["factor_id"] for r in delivered if str(r.get("risk_exposure", "")).lower() == "true"]
    check.add(not exposed, "no risk exposures in the package", f"{len(exposed)} offenders")
    # The gates that failed must be recorded for anything rejected.
    rejected = [r for r in rows if r.get("status") == "rejected"]
    unexplained = [r["factor_id"] for r in rejected if not (r.get("failed_gates") or "").strip()]
    check.add(
        not unexplained,
        "every rejection names its gate",
        f"{len(rejected)} rejected, {len(unexplained)} without a recorded gate",
    )

    # ── supplementary layer ──────────────────────────────────────────
    supplementary = load_json(delivery / "supplementary_report.json")
    if supplementary is None:
        check.add(False, "supplementary_report.json", "missing")
    else:
        summary = supplementary.get("summary") or {}
        checked = summary.get("n_tested")
        check.add(
            isinstance(checked, int) and checked > 0,
            "FDR computed over the tested set",
            f"n_tested={checked}, n_accepted={summary.get('n_accepted')}, q={summary.get('q')}",
        )
        marked = [r for r in rows if str(r.get("fdr_accepted", "")).lower() == "true"]
        check.add(
            len(marked) == summary.get("n_accepted"),
            "manifest fdr_accepted agrees with the report",
            f"manifest marks {len(marked)}, report says {summary.get('n_accepted')}",
        )
        with_retention = [
            r for r in delivered
            if str(r.get("industry_neutral_retention", "")).strip() not in ("", "nan", "None")
        ]
        check.add(
            len(with_retention) == len(delivered),
            "industry-neutral retention present for every delivered factor",
            f"{len(with_retention)}/{len(delivered)}",
        )

    # ── out-of-sample demo ───────────────────────────────────────────
    backtests = load_json(delivery / "strategy_demos" / "backtest_results.json")
    if backtests is None:
        check.add(False, "strategy_demos/backtest_results.json", "missing")
    else:
        results = backtests.get("results") or {}
        window = backtests.get("backtest_window") or {}
        check.add(len(results) >= 1, "out-of-sample strategies reported",
                  f"{len(results)} variants, window {window.get('start')}..{window.get('end')}")
        complete = [
            name for name, payload in results.items()
            if (payload.get("metrics") or {}).get("total_return") is not None
        ]
        check.add(len(complete) == len(results), "every variant has metrics",
                  f"{len(complete)}/{len(results)}")
    clusters = load_json(delivery / "strategy_demos" / "clusters.json")
    check.add(
        clusters is not None and bool(clusters.get("representatives")),
        "clusters.json with representatives",
        "present" if clusters else "missing",
    )

    # ── live signals ─────────────────────────────────────────────────
    signals_dir = delivery / "live_signals"
    for name in ("file_orders.csv", "conditional_orders.json", "supabase_rows.json",
                 "signal_summary.json"):
        check.add((signals_dir / name).is_file(), f"live_signals/{name}",
                  "present" if (signals_dir / name).is_file() else "MISSING")
    orders = signals_dir / "file_orders.csv"
    if orders.is_file():
        with orders.open(encoding="utf-8-sig", newline="") as handle:
            order_rows = list(csv.DictReader(handle))
        check.add(bool(order_rows), "file orders are non-empty", f"{len(order_rows)} orders")
        raw = orders.read_bytes()[:3]
        check.add(raw == b"\xef\xbb\xbf", "file orders carry a UTF-8 BOM",
                  "yes (QMT-friendly)" if raw == b"\xef\xbb\xbf" else f"no, starts {raw!r}")
    supabase = load_json(signals_dir / "supabase_rows.json")
    if supabase is not None:
        pushed = [r for r in (supabase if isinstance(supabase, list) else supabase.get("rows", []))
                  if r.get("pushed") is True]
        check.add(not pushed, "no rows claim to have been pushed",
                  f"{len(pushed)} rows marked pushed (the repo has no Supabase client)")

    # ── auditable package ────────────────────────────────────────────
    package = load_json(delivery / "package" / "package_manifest.json")
    if package is None:
        check.add(False, "package/package_manifest.json", "missing")
    else:
        counts = package.get("counts") or {}
        check.add(
            counts.get("included") == len(delivered),
            "package agrees with the manifest",
            f"package included {counts.get('included')}, manifest says {len(delivered)}",
        )
        factor_dirs = list((delivery / "package" / "factors").glob("*"))
        check.add(
            len(factor_dirs) >= len(delivered),
            "per-factor evidence copied",
            f"{len(factor_dirs)} directories for {len(delivered)} delivered factors",
        )

    # ── independent cross-check ──────────────────────────────────────
    cross = load_json(delivery / "cross_check.json")
    if cross is None:
        check.add(False, "cross_check.json", "missing")
    else:
        check.add(cross.get("finding_count") == 0, "cross-check found nothing",
                  f"finding_count={cross.get('finding_count')}")

    # ── the generated cover page ─────────────────────────────────────
    readme = delivery / "README.md"
    check.add(readme.is_file(), "README.md", "present" if readme.is_file() else "missing")
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        states_target = f"达成 300 的目标：**{'是' if len(delivered) >= target else '否'}**" in text
        check.add(states_target, "README states the target truthfully",
                  "agrees with the manifest" if states_target else "DISAGREES with the manifest")

    return check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--delivery-dir", required=True)
    parser.add_argument("--target", type=int, default=TARGET)
    args = parser.parse_args(argv)

    delivery = Path(args.delivery_dir)
    if not delivery.is_dir():
        print(f"delivery directory not found: {delivery}")
        return 2
    check = verify(delivery, target=args.target)
    print(check.report())
    print()
    if check.failed:
        print(f"FAILED: {len(check.failed)} of {len(check.rows)} checks")
        return 1
    print(f"PASSED: all {len(check.rows)} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
