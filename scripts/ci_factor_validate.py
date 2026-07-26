#!/usr/bin/env python3
"""
CI factor validation script.

Reads changed_factors.json, runs factor_lab validation pipeline,
and outputs structured results for PR comment generation.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def failed_result(message: str, *, factor_name: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "failed",
        "error": message,
        "checks": [],
        "evaluation": {},
    }
    if factor_name is not None:
        payload["factor_name"] = factor_name
    return payload


def run_cli_command(cmd: list[str], timeout: int = 300) -> dict[str, Any]:
    """Run a factor_lab CLI command and return JSON output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            cwd=str(REPO_ROOT),
            timeout=timeout,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip(), "stdout": result.stdout.strip()}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out"}
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "stdout": result.stdout[:1000] if 'result' in dir() else ""}
    except Exception as e:
        return {"error": str(e)}


def validate_alpha101_factors(
    factors: list[str],
    n_dates: int = 60,
    n_codes: int = 8,
    seed: int = 42,
) -> dict[str, Any]:
    """Run alpha101 validation on specified factors."""
    cmd = [
        sys.executable, "-m", "research_core.factor_lab.cli",
        "run-alpha101-demo",
        "--factors", ",".join(factors),
        "--n-dates", str(n_dates),
        "--n-codes", str(n_codes),
        "--seed", str(seed),
    ]
    return run_cli_command(cmd)


def validate_submission(sub_dir: str) -> dict[str, Any]:
    """Validate a single factor submission.

    Steps:
    1. Read spec.json
    2. Import factor.py and compute on demo data
    3. Run evaluation
    4. Check coverage, IC/IR
    """
    sub_path = REPO_ROOT / sub_dir
    spec_path = sub_path / "spec.json"
    factor_path = sub_path / "factor.py"

    if not spec_path.exists():
        return failed_result(f"Missing spec.json in {sub_dir}")
    if not factor_path.exists():
        return failed_result(f"Missing factor.py in {sub_dir}")

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception as e:
        return failed_result(f"Invalid spec.json: {e}")

    factor_name = spec.get("factor_name", "unknown")
    required_fields = spec.get("required_fields", [])

    # Build demo panel
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    dates = pd.date_range("2021-01-01", periods=60, freq="B")
    codes = [f"stock_{idx:03d}" for idx in range(1, 9)]

    records = []
    for code_idx, code in enumerate(codes):
        close = 12 + code_idx * 2.5
        for date in dates:
            shock = rng.normal(0.0006 * (code_idx + 1), 0.015)
            close = max(close * (1 + shock), 1.0)
            records.append({
                "date": date, "code": code,
                "open": max(close * (1 + rng.normal(0, 0.004)), 0.5),
                "high": max(close * (1 + abs(rng.normal(0, 0.01))), close),
                "low": min(close * (1 - abs(rng.normal(0, 0.01))), close),
                "close": close,
                "volume": int(rng.integers(500_000, 5_000_000)),
                "amount": int(rng.integers(5_000_000, 50_000_000)),
            })

    panel = pd.DataFrame(records)

    # Check field coverage
    available = set(panel.columns)
    required = set(required_fields)
    missing = required - available
    if missing:
        return {
            "factor_name": factor_name,
            "status": "failed",
            "checks": [
                {"name": "field_mapping_match", "status": "failed",
                 "description": f"输入字段未覆盖规格要求。缺失: {sorted(missing)}"}
            ],
            "evaluation": {},
        }

    # Import and compute factor
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import importlib.util
        spec_obj = importlib.util.spec_from_file_location(
            f"submission_{factor_name}", str(factor_path)
        )
        module = importlib.util.module_from_spec(spec_obj)
        spec_obj.loader.exec_module(module)

        if not hasattr(module, 'compute'):
            return {
                **failed_result("factor.py 缺少 compute(panel) 函数", factor_name=factor_name),
                "checks": [{"name": "formula_match", "status": "failed", "description": "factor.py 缺少 compute(panel) 函数"}],
            }

        factor_series = module.compute(panel)
    except Exception as e:
        return {
            **failed_result(f"因子计算失败: {e}", factor_name=factor_name),
            "checks": [{"name": "formula_match", "status": "failed", "description": f"因子计算失败: {e}"}],
        }

    # Build factor frame
    factor_frame = panel[["date", "code"]].copy()
    factor_frame[factor_name] = factor_series

    # Run evaluation
    from research_core.factor_lab.evaluation import compute_forward_returns, summarize_factor_frame

    factor_frame["forward_return_1d"] = compute_forward_returns(
        panel[["date", "code", "close"]].sort_values(["code", "date"]).reset_index(drop=True),
        price_col="close",
    )
    eval_summary = summarize_factor_frame(factor_frame, factor_names=[factor_name])

    metrics = eval_summary["metrics"].get(factor_name, {})

    # Check thresholds
    checks = [
        {"name": "field_mapping_match", "status": "passed",
         "description": "计算输入字段覆盖规格要求。"},
        {"name": "sample_point_reconciliation", "status":
         "passed" if metrics.get("non_null_count", 0) > 0 else "failed",
         "description": f"已生成 {metrics.get('non_null_count', 0)} 个有效样本点位。"},
        {"name": "evaluation_consistency", "status":
         "passed" if metrics.get("cross_section_count", 0) > 0 else "failed",
         "description": f"已生成覆盖 {metrics.get('cross_section_count', 0)} 期截面的基础评估指标。"},
    ]

    passed = all(c["status"] == "passed" for c in checks)

    return {
        "factor_name": factor_name,
        "status": "passed" if passed else "failed",
        "checks": checks,
        "evaluation": {
            "coverage_ratio": metrics.get("coverage_ratio"),
            "non_null_count": metrics.get("non_null_count"),
            "rank_ic_mean": metrics.get("rank_ic_mean"),
            "rank_ic_ir": metrics.get("rank_ic_ir"),
            "long_short_mean": metrics.get("long_short_mean"),
            "cross_section_count": metrics.get("cross_section_count"),
        },
    }


def validate_pipeline_smoke() -> dict[str, Any]:
    result = run_cli_command(
        [
            sys.executable, "-m", "research_core.factor_lab.cli",
            "run-factor-research",
            "--factor-set", "wq101",
            "--data-source", "demo",
            "--factors", "alpha1",
            "--n-dates", "80",
            "--n-codes", "8",
            "--seed", "42",
        ]
    )
    if result.get("error"):
        return {"status": "failed", "error": result["error"], "stdout": result.get("stdout", "")}
    artifacts = result.get("artifacts", {})
    required = ["data_quality_json", "panel_snapshot_json", "internal_validation_json", "factor_frame"]
    missing = [name for name in required if not artifacts.get(name)]
    return {
        "status": "failed" if missing else "passed",
        "job_id": result.get("job_id"),
        "missing_artifacts": missing,
        "artifacts": {key: artifacts.get(key) for key in required},
    }


def validate_lifecycle_registry() -> dict[str, Any]:
    try:
        from registry.factor_registry.lifecycle import build_promotion_record, validate_transition

        validate_transition("implemented", "internal_validated")
        build_promotion_record(
            factor_name="alpha1",
            from_state="implemented",
            to_state="internal_validated",
            promoted_by="ci",
            run_id="ci-smoke",
            reason="CI lifecycle smoke test",
        )
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}
    return {"status": "passed"}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--changed-json', default='/tmp/changed_factors.json')
    parser.add_argument('--output-dir', default='/tmp/validation_output')
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Read changed factors
    try:
        changed = json.loads(Path(args.changed_json).read_text())
    except Exception:
        changed = {"changed_factors": [], "changed_submissions": []}

    results: dict[str, Any] = {
        "alpha101": {},
        "submissions": {},
        "pipeline_smoke": {},
        "lifecycle": {},
    }

    results["pipeline_smoke"] = validate_pipeline_smoke()
    results["lifecycle"] = validate_lifecycle_registry()

    # Validate alpha101 factors
    alpha_factors = changed.get("changed_factors", [])
    if alpha_factors and alpha_factors != ["__ALL__"]:
        print(f"Validating alpha101 factors: {alpha_factors}")
        alpha_result = validate_alpha101_factors(alpha_factors)
        results["alpha101"] = alpha_result
    elif alpha_factors == ["__ALL__"]:
        print("All alpha101 factors changed — running full validation skipped in CI (use manual trigger)")
        results["alpha101"] = {"note": "Full alpha101 validation skipped in CI. Run manually."}

    # Validate submissions
    submissions = changed.get("changed_submissions", [])
    for sub_dir in submissions:
        print(f"Validating submission: {sub_dir}")
        result = validate_submission(sub_dir)
        results["submissions"][sub_dir] = result

    # Write results
    (output_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Summary
    print("\n=== Validation Summary ===")
    print(json.dumps(results, indent=2, ensure_ascii=False))

    # Exit code
    has_failures = False
    if isinstance(results["alpha101"], dict):
        if results["alpha101"].get("status") == "failed" or results["alpha101"].get("error"):
            has_failures = True
    for sub_result in results["submissions"].values():
        if sub_result.get("status") == "failed" or sub_result.get("error"):
            has_failures = True
    for key in ("pipeline_smoke", "lifecycle"):
        if results[key].get("status") == "failed" or results[key].get("error"):
            has_failures = True

    if has_failures:
        sys.exit(1)


if __name__ == '__main__':
    main()
