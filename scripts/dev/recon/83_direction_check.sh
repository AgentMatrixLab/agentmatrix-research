REPO=/home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
cd $REPO || exit 1
export PYTHONPATH=$REPO

echo "=== 1. OOS 结果里是否带训练段 IC（用于定方向，避免用样本外挑方向）==="
$PY -X utf8 - <<'PYEOF'
import glob, json
paths = sorted(glob.glob("/home/data/agentmatrix_run/runtime_mirror/data/factor_lab/validation_runs/*/validation_result.json"))
print("  结果数:", len(paths))
for p in paths[:6]:
    d = json.load(open(p))
    if d.get("status") != "validated":
        continue
    fields = sorted(d.keys())
    print("  ---", d.get("factor_id"))
    print("     top-level:", fields)
    print("     training:", json.dumps(d.get("training"), ensure_ascii=False)[:220])
    rk = d.get("rank_ic") or {}
    for h, v in list(rk.items())[:3]:
        if isinstance(v, dict):
            print("     rank_ic[%s].mean = %s" % (h, v.get("mean")))
    break

print()
print("=== 2. 方向一致性：训练段 IC 与样本外 IC 的符号 ===")
rows = []
for p in paths:
    d = json.load(open(p))
    if d.get("status") != "validated" or d.get("failed_gates"):
        continue
    train = (d.get("training") or {}).get("primary_rank_ic_mean")
    rk = d.get("rank_ic") or {}
    primary = None
    for key in ("10d", "10"):
        if key in rk and isinstance(rk[key], dict):
            primary = rk[key].get("mean")
            break
    if primary is None and rk:
        first = list(rk.values())[0]
        primary = first.get("mean") if isinstance(first, dict) else None
    rows.append((d.get("factor_id"), train, primary))

same = sum(1 for _, t, o in rows if t is not None and o is not None and (t > 0) == (o > 0))
neg_train = sum(1 for _, t, _ in rows if t is not None and t < 0)
print("  通过门槛且有 train/pos IC 的因子:", len(rows))
print("  训练段 IC 为负（即反向因子）的个数:", neg_train)
print("  训练与样本外 IC 同号:", same, "/", len(rows))
print()
for fid, t, o in rows[:14]:
    print("    %-26s train_ic=%-12s oos_ic=%-12s 方向=%s" % (
        fid,
        "None" if t is None else round(t, 5),
        "None" if o is None else round(o, 5),
        "未定" if t is None else ("正向" if t > 0 else "反向")))
PYEOF

echo
echo "=== 3. 彩排回测指标（含新基准）==="
$PY -X utf8 - <<'PYEOF'
import json
d = json.load(open("/home/data/agentmatrix_run/rehearsal/strategy_demos/backtest_results.json"))
print("  benchmark:", str(d.get("benchmark"))[:110])
print("  missing_price_policy:", d.get("missing_price_policy"), " priced:", d.get("priced_names"))
for k, v in d.get("results", {}).items():
    m = v.get("metrics", {})
    print("    %-18s ann=%-9s bench=%-9s excess=%-9s vol=%-9s mdd=%s" % (
        k,
        round(m.get("annualized_return", float("nan")), 4),
        round(m.get("benchmark_return", float("nan")), 4),
        round(m.get("excess_return", float("nan")), 4),
        round(m.get("volatility", float("nan")), 4),
        round(m.get("max_drawdown", float("nan")), 4)))
PYEOF

echo
echo "=== 4. 实盘信号产物 ==="
ls -la /home/data/agentmatrix_run/rehearsal/live_signals/
head -4 /home/data/agentmatrix_run/rehearsal/live_signals/file_orders.csv
date -Is
