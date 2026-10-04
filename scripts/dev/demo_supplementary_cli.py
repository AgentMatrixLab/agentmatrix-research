"""Exercise the supplementary CLI end to end on fabricated validation output.

TEST-ONLY. The validation_result.json files written here are synthetic and are
not evidence about any factor.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (factor_id, t_stat, days)
CASES = [
    ("strong_a", 6.2, 420),
    ("strong_b", 4.8, 420),
    ("marginal_a", 1.90, 420),
    ("marginal_b", 1.80, 420),
    ("marginal_c", 1.72, 420),
    ("noise_a", 1.30, 420),
    ("noise_b", 0.40, 420),
    ("too_short", 5.0, 1),
]


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="amr-supp-"))
    runs = workdir / "validation_runs"
    for factor_id, t_stat, days in CASES:
        target = runs / factor_id
        target.mkdir(parents=True, exist_ok=True)
        (target / "validation_result.json").write_text(
            json.dumps(
                {
                    "factor_id": factor_id,
                    "primary_horizon": 10,
                    "rank_ic": {
                        "10": {
                            "mean": 0.02,
                            "ic_ir": 0.3,
                            "t_stat": t_stat,
                            "days": days,
                            "yearly": {},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    out = workdir / "supplementary_report.json"
    proc = subprocess.run(
        [
            sys.executable, "-X", "utf8",
            str(ROOT / "scripts" / "run_robustness_supplement.py"),
            "--runs-dir", str(runs),
            "--out", str(out),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
        return proc.returncode

    report = json.loads(out.read_text(encoding="utf-8"))
    summary = report["summary"]
    print("summary:", summary)
    by_id = {item["factor_id"]: item for item in report["factors"]}
    print()
    for factor_id, t_stat, days in CASES:
        item = by_id[factor_id]
        print(
            f"  {factor_id:<12} t={t_stat:>5}  p={item['p_value']:.4g}  "
            f"padj={item['p_adjusted']:.4g}  fdr={item['fdr_accepted']}"
        )

    markdown = out.with_suffix(".md")
    print(f"\nmarkdown exists: {markdown.exists()} ({markdown.stat().st_size} bytes)")

    ok = (
        by_id["strong_a"]["fdr_accepted"]
        and by_id["strong_b"]["fdr_accepted"]
        and not by_id["noise_a"]["fdr_accepted"]
        and not by_id["noise_b"]["fdr_accepted"]
        and not by_id["too_short"]["fdr_accepted"]
        and summary["n_submitted"] == len(CASES)
        and summary["n_accepted"] < summary["n_submitted"]
    )
    shutil.rmtree(workdir, ignore_errors=True)
    print("\nRESULT:", "OK" if ok else "UNEXPECTED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
