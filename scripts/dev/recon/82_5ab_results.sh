RUN=/home/data/agentmatrix_run
REH=$RUN/rehearsal
PY=/home/data/conda-envs/rqsdk/bin/python

echo "=== 5ab 日志 ==="
cat "$REH/run_5ab.log" 2>/dev/null | tail -40

echo
echo "=== strategy_demos ==="
ls -la "$REH/strategy_demos/" 2>/dev/null
$PY -X utf8 - <<'PYEOF'
import json, os
base = "/home/data/agentmatrix_run/rehearsal/strategy_demos"
sp = os.path.join(base, "strategies.json")
if os.path.exists(sp):
    d = json.load(open(sp))
    print("  data_status:", d.get("data_status"))
    for s in d.get("strategies", []):
        print("    %-32s n_factors=%-3s traded=%s" % (
            s["strategy_id"], s["n_factors"], round(s.get("mean_traded_fraction") or 0, 4)))
    print("  策略数:", len(d.get("strategies", [])))
bp = os.path.join(base, "backtest_results.json")
if os.path.exists(bp):
    d = json.load(open(bp))
    print("  benchmark:", str(d.get("benchmark"))[:80])
    print("  missing_price_policy:", d.get("missing_price_policy"), " priced_names:", d.get("priced_names"))
    print("  window:", d.get("backtest_window"))
    for k, v in d.get("results", {}).items():
        m = v.get("metrics", {})
        print("    %-32s ann=%-9s bench=%-9s excess=%-9s sharpe=%-7s vol=%-8s mdd=%s" % (
            k,
            round(m.get("annualized_return", float("nan")), 4),
            round(m.get("benchmark_return", float("nan")), 4),
            round(m.get("excess_return", float("nan")), 4),
            round(m.get("sharpe", float("nan")), 3) if isinstance(m.get("sharpe"), (int, float)) else "-",
            round(m.get("volatility", float("nan")), 4),
            round(m.get("max_drawdown", float("nan")), 4) if isinstance(m.get("max_drawdown"), (int, float)) else "-"))
PYEOF

echo
echo "=== live_signals ==="
ls -la "$REH/live_signals/" 2>/dev/null || echo "  尚未产出"
$PY -X utf8 - <<'PYEOF'
import json, os, csv
d = "/home/data/agentmatrix_run/rehearsal/live_signals"
s = os.path.join(d, "signal_summary.json")
if os.path.exists(s):
    print("  summary:", json.dumps(json.load(open(s)), ensure_ascii=False)[:600])
csvp = os.path.join(d, "file_orders.csv")
if os.path.exists(csvp):
    with open(csvp, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    print("  文件单行数:", len(rows))
    for r in rows[:5]:
        print("   ", r)
ro = os.path.join(d, "supabase_rows.json")
if os.path.exists(ro):
    p = json.load(open(ro))
    print("  supabase rows:", len(p["rows"]), " pushed:", p["pushed"], " key:", p["upsert_key"])
    if p["rows"]:
        print("   row[0]:", json.dumps(p["rows"][0], ensure_ascii=False))
PYEOF

echo
echo "=== pool 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  parts   : $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "    arg=" $NF, "etime=" $2}'
date -Is
