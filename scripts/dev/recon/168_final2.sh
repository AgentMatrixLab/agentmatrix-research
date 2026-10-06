RUN=/home/data/agentmatrix_run
echo "################ 实盘信号 ################"
cat "$RUN/delivery/live_signals/signal_summary.json" 2>/dev/null
echo
echo "  文件:"
ls -la "$RUN/delivery/live_signals/" 2>/dev/null | tail -6 | sed 's/^/    /'
echo
echo "  文件单前 4 行:"
head -4 "$RUN/delivery/live_signals/file_orders.csv" 2>/dev/null | sed 's/^/    /'
echo
echo "  条件单样例:"
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import json
try:
    d = json.load(open("/home/data/agentmatrix_run/delivery/live_signals/conditional_orders.json"))
    items = d if isinstance(d, list) else d.get("orders", [])
    print("    条数:", len(items))
    if items:
        print("    ", json.dumps(items[0], ensure_ascii=False)[:240])
except Exception as e:
    print("    读取失败:", e)
PYEOF
echo
echo "################ 交付目录 ################"
ls -la "$RUN/delivery" 2>/dev/null | sed 's/^/  /'
echo
echo "################ README（生成的那一页）前 14 行 ################"
head -14 "$RUN/delivery/README.md" 2>/dev/null | sed 's/^/  /'
echo
echo "################ 补充层 ################"
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import json
d = json.load(open("/home/data/agentmatrix_run/delivery/supplementary_report.json"))
s = d.get("summary") or {}
m = d.get("marginal_effect") or {}
print("  FDR:", json.dumps(s, ensure_ascii=False))
print("  边际效应:", json.dumps(m, ensure_ascii=False)[:200])
PYEOF
echo
echo "################ 资源与守护终态 ################"
echo "  磁盘可用: $(df -h / | awk 'NR==2{print $4}')"
echo "  内存可用: $(free -g | awk '/^Mem:/{print $7}')GB"
echo "  仍在跑的守护: $(ps -eo args | awk '/retain_passing|mirror_runtime|pool_watchdog|auto_deliver|run_pool/ && !/awk/ {c++} END {print c+0}') 个（交付后 pool/watchdog/auto 应已退出）"
date -Is
