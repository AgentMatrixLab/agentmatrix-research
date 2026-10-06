RUN=/home/data/agentmatrix_run
echo "################ 1. 验收裁决（23 项逐条）################"
cat "$RUN/logs/auto_deliver_acceptance.log" 2>/dev/null

echo
echo "################ 2. 交付清单摘要 ################"
cat "$RUN/delivery/delivery_manifest.summary.json" 2>/dev/null

echo
echo "################ 3. 交叉验证 ################"
cat "$RUN/delivery/cross_check.json" 2>/dev/null

echo
echo "################ 4. 可审计包 ################"
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import json
d = json.load(open("/home/data/agentmatrix_run/delivery/package/package_manifest.json"))
print("  counts:", json.dumps(d.get("counts"), ensure_ascii=False))
print("  rule  :", json.dumps(d.get("rule"), ensure_ascii=False)[:200])
exc = d.get("excluded_factors") or []
print("  排除样例（含具体失败数值）:")
for e in exc[:3]:
    print("   ", json.dumps({k: e.get(k) for k in ("factor_id", "failed_gates", "reason")},
                            ensure_ascii=False)[:230])
PYEOF

echo
echo "################ 5. 样本外策略结果 ################"
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import json
d = json.load(open("/home/data/agentmatrix_run/delivery/strategy_demos/backtest_results.json"))
w = d.get("backtest_window") or {}
print("  窗口 %s ~ %s" % (w.get("start"), w.get("end")))
print("  %-22s %10s %10s %10s %10s %10s" % ("变体", "累计", "年化", "基准", "超额", "最大回撤"))
for name, payload in (d.get("results") or {}).items():
    m = payload.get("metrics") or {}
    def p(k):
        v = m.get(k)
        return "—" if not isinstance(v, (int, float)) else "%.2f%%" % (100 * v)
    print("  %-22s %10s %10s %10s %10s %10s" % (
        name.replace("delivery_", "").replace("_v1", ""),
        p("total_return"), p("annualized_return"), p("benchmark_return"),
        p("excess_return"), p("max_drawdown")))
PYEOF

echo
echo "################ 6. 实盘信号 ################"
cat "$RUN/delivery/live_signals/signal_summary.json" 2>/dev/null | head -30
echo "  产物:"
ls -la "$RUN/delivery/live_signals/" 2>/dev/null | tail -5 | sed 's/^/    /'

echo
echo "################ 7. 交付目录 ################"
ls -la "$RUN/delivery" 2>/dev/null | sed 's/^/  /'
echo "  磁盘可用: $(df -h / | awk 'NR==2{print $4}')"
date -Is
