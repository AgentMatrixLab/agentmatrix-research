"""
报告生成 — JSON + 终端摘要（纯因子层）
"""

import json
from datetime import datetime
from pathlib import Path


def generate_report(result, output_path=""):
    report = {
        "generated_at": datetime.now().isoformat(),
        "verdict": result.get("verdict", "UNKNOWN"),
        "stages": {},
    }
    s0 = result.get("S0_quick_filter", {})
    report["stages"]["S0_IC"] = {"passed": s0.get("passed"), "icir": s0.get("icir_annual"),
                                  "direction": s0.get("direction"), "monotonic": s0.get("monotonic")}
    s1 = result.get("S1_monthly_ic", {})
    report["stages"]["S1_monthly"] = {"passed": s1.get("passed"), "monthly_icir": s1.get("monthly_icir"),
                                       "consistent": s1.get("consistency_ok"),
                                       "declining": s1.get("declining")}
    report["stages"]["S2_cscv"] = result.get("S2_cscv_pbo", {})
    report["stages"]["S3_decay"] = result.get("S3_alpha_decay", {})
    s4 = result.get("S4_quantile_spread", {})
    report["stages"]["S4_spread"] = {"passed": s4.get("passed"), "tstat": s4.get("daily_spread_tstat"),
                                      "dir_match": s4.get("daily_direction_match")}
    if output_path:
        path = Path(output_path)
        if path.suffix != ".json": path = path / "factor_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        report["saved_to"] = str(path)
    return report


def print_summary(result):
    print()
    print("=" * 65)
    print("  因子质量验证（纯因子层）")
    print("  Grinold&Kahn + Lopez de Prado + Lee 2025")
    print("=" * 65)

    v = result.get("verdict", "UNKNOWN")
    s = "✅" if "PASS" in v else "⚠️" if "WARNING" in v else "❌"
    print(f"\n  最终判断: {s} {v}")

    s0 = result.get("S0_quick_filter", {})
    print(f"\n  S0 IC筛选 {'✅' if s0.get('passed') else '❌'} — ICIR: {s0.get('icir_annual')}  方向: {s0.get('direction')}  单调: {s0.get('monotonic')}")

    s1 = result.get("S1_monthly_ic", {})
    print(f"  S1 月度稳定 {'✅' if s1.get('passed') else '❌'} — 月ICIR: {s1.get('monthly_icir')}  方向一致: {s1.get('consistency_ok')}  衰减趋势: {s1.get('declining')}")

    s2 = result.get("S2_cscv_pbo", {})
    print(f"  S2 CSCV/PBO {'✅' if s2.get('pbo_passed') else '❌'} — PBO: {s2.get('pbo')}")

    s3 = result.get("S3_alpha_decay", {})
    print(f"  S3 衰减建模      — {s3.get('best_model')} R²={s3.get('best_r2')}  半衰期: {s3.get('half_life_years')}年  {s3.get('decay_severity')}")

    s4 = result.get("S4_quantile_spread", {})
    print(f"  S4 分位价差 {'✅' if s4.get('passed') else '❌'} — t={s4.get('daily_spread_tstat')}  方向匹配: {s4.get('daily_direction_match')}")

    print("\n" + "=" * 65)
    if result.get("report", {}).get("saved_to"):
        print(f"  报告: {result['report']['saved_to']}")
    print()
