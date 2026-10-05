PY=/home/data/conda-envs/rqsdk/bin/python
REH=/home/data/agentmatrix_run/rehearsal
RUN=/home/data/agentmatrix_run

echo "=== 回测指标（方向修正后）==="
$PY -X utf8 - <<'PYEOF'
import json
d = json.load(open("/home/data/agentmatrix_run/rehearsal/strategy_demos/backtest_results.json"))
print("  benchmark :", str(d.get("benchmark"))[:100])
print("  policy    :", d.get("missing_price_policy"), "| priced:", d.get("priced_names"))
print("  window    :", d.get("backtest_window"))
print("  direction :", str(d.get("direction_source"))[:80])
print()
hdr = "%-22s %9s %9s %9s %9s %9s %7s" % ("variant", "total", "ann", "bench", "excess", "maxdd", "traded")
print("  " + hdr)
for k, v in d.get("results", {}).items():
    m = v.get("metrics", {})
    print("  %-22s %9.4f %9.4f %9.4f %9.4f %9.4f" % (
        k.replace("delivery_", "").replace("_v1", ""),
        m.get("total_return", float("nan")),
        m.get("annualized_return", float("nan")),
        m.get("benchmark_return", float("nan")),
        m.get("excess_return", float("nan")),
        m.get("max_drawdown", float("nan"))))
    print("      turnover_basis=%s n_dates=%s" % (
        v.get("turnover_basis"), len(v.get("dates", []))))
print()
dirs = d.get("factor_directions", {})
rev = [k for k, v in dirs.items() if v is not None and v < 0]
print("  因子方向: 共 %d, 反向 %d" % (len(dirs), len(rev)))
PYEOF

echo
echo "=== 实盘信号（方向修正后）==="
$PY -X utf8 - <<'PYEOF'
import json, csv
d = "/home/data/agentmatrix_run/rehearsal/live_signals"
s = json.load(open(d + "/signal_summary.json"))
print("  strategy_id :", s["strategy_id"])
print("  trade_date  :", s["trade_date"])
print("  core        :", s["core_factors"])
print("  directions  :", s.get("factor_directions"))
print("  targets=%s orders=%s buys=%s sells=%s" % (
    s["n_targets"], s["n_orders"], s["n_buys"], s["n_sells"]))
with open(d + "/file_orders.csv", encoding="utf-8-sig") as fh:
    rows = list(csv.DictReader(fh))
print("  文件单前 3 行:")
for r in rows[:3]:
    print("   ", r)
c = json.load(open(d + "/conditional_orders.json"))
print("  条件单 orders:", len(c["orders"]), " 首条:", json.dumps(c["orders"][0], ensure_ascii=False))
sup = json.load(open(d + "/supabase_rows.json"))
print("  supabase rows:", len(sup["rows"]), " pushed:", sup["pushed"], " table:", sup["table"])
PYEOF

echo
echo "=== pool 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  parts   : $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "    arg=" $NF, "etime=" $2}'
echo "  镜像结果: $(find $RUN/runtime_mirror/data/factor_lab/validation_runs -name validation_result.json 2>/dev/null | wc -l)"
date -Is
