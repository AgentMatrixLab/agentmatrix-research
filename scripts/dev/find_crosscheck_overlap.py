"""Find which RQData factors our own catalog can reproduce, for cross-validation.

RQData ships 300 daily factor values. Our catalog contains a TDXGS family written
in the same 通达信 idiom, so where the two overlap we can compute the factor with
our own engine and correlate it against RQData's independent implementation. That
is a real check on the engine -- an external oracle, not our own tests.

This only reads local files, so it runs whether or not the server is reachable.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CATALOG = ROOT / "pages" / "factor-db-dashboard" / "data" / "factors.json"

# Names observed in the server's rqdata.stock_factor_daily_long (300 with values).
# Recorded from the reconnaissance queries; the live list is read from ClickHouse
# when the server is up, this is the offline fallback.
RQDATA_OBSERVED = """
ACCER ADTM ADX ADXR AMP1 AMP10 AMP20 AMP3 AMP5 AMP60 AMV20 AMV5 AMV60 AR
AROON_DOWN AROON_UP ASI ASIT ATR BBI BIAS BOLL CCI CR DDI DMA DMI DPO EMV
ENE EXPMA KDJ LWR MACD MFI MTM OBV OSC PSY PVT ROC RSI SAR SMI SRDM TRIX
VR VSTD WR WVAD
""".split()


def normalize(name: str) -> str:
    """Fold a factor name to a comparable key.

    Family prefixes, separators and the parameter suffix all differ between the
    two sides (`TDXGS_ATR_14` vs `ATR`), so compare the leading identifier only.
    """
    cleaned = name.split(":")[-1].upper()
    cleaned = re.sub(r"^TDXGS_?", "", cleaned)
    cleaned = re.sub(r"[^A-Z0-9]+", "_", cleaned).strip("_")
    return cleaned


def main() -> int:
    factors = json.loads(CATALOG.read_text(encoding="utf-8"))["factors"]
    tdx = [f for f in factors if f["factor_id"].upper().startswith("TDXGS")]

    ours: dict[str, list[dict]] = {}
    for factor in tdx:
        base = normalize(factor["factor_id"])
        # Keep the leading token as the family key: ATR_14 -> ATR
        key = base.split("_")[0]
        ours.setdefault(key, []).append(factor)

    rq = sorted({normalize(name).split("_")[0] for name in RQDATA_OBSERVED})
    overlap = sorted(set(ours) & set(rq))
    only_ours = sorted(set(ours) - set(rq))
    only_rq = sorted(set(rq) - set(ours))

    print(f"我们的 TDXGS 因子: {len(tdx)} 条, {len(ours)} 个指标族")
    print(f"RQData 观测到的指标: {len(rq)} 个")
    print()
    print(f"★ 可交叉验证（两边都有）: {len(overlap)} 个")
    for key in overlap:
        variants = ", ".join(f["factor_id"] for f in ours[key])
        print(f"    {key:<12} 我们的: {variants}")
    print()
    print(f"仅我们有 ({len(only_ours)}): {', '.join(only_ours[:20])}")
    print()
    print(f"仅 RQData 有 ({len(only_rq)}): {', '.join(only_rq[:30])}")
    print()
    if overlap:
        print("结论：这", len(overlap), "个指标可以用 RQData 的独立实现交叉验证我们的引擎。")
        print("做法：对每个重叠指标，取我们的因子值与 RQData 的因子值，按 (date, code) 对齐后算秩相关。")
        print("预期：秩相关 > 0.95 视为实现一致；低于此值需要逐条查口径差异（复权、窗口、平滑）。")
    else:
        print("结论：没有重叠，无法直接交叉验证；只能靠双方各自的定义文档比对。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
