"""从 Supabase 真值库导出 alpha013 切片，造"真实真值"场景的验收样本。"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "factor_lab" / "samples"
OUT.mkdir(parents=True, exist_ok=True)

base_url = os.environ.get("FACTOR_LAB_SUPABASE_URL", "").rstrip("/")
key = os.environ.get("FACTOR_LAB_SUPABASE_WRITE_KEY", "")
if not base_url or not key:
    print("缺少 FACTOR_LAB_SUPABASE_URL / FACTOR_LAB_SUPABASE_WRITE_KEY", file=sys.stderr)
    raise SystemExit(2)

url = (
    f"{base_url}/rest/v1/factor_truth_values"
    f"?select=symbol,trade_date,truth_value"
    f"&factor_family=eq.alpha101&factor_name=eq.WorldQuant_alpha013"
    f"&order=trade_date.desc&limit=300"
)
req = urllib.request.Request(url, headers={"apikey": key, "Authorization": f"Bearer {key}"})
with urllib.request.urlopen(req, timeout=60) as resp:
    rows = json.loads(resp.read().decode("utf-8"))

header = "symbol,trade_date,factor_value\n"
with open(OUT / "alpha013_truth_slice_pass.csv", "w", encoding="utf-8") as f:
    f.write(header)
    for r in rows:
        f.write(f"{r['symbol']},{r['trade_date']},{r['truth_value']}\n")

with open(OUT / "alpha013_truth_slice_perturbed.csv", "w", encoding="utf-8") as f:
    f.write(header)
    for r in rows:
        f.write(f"{r['symbol']},{r['trade_date']},{r['truth_value'] * 1.5 + 0.001}\n")

print(f"导出 {len(rows)} 行 -> {OUT}")