RUN=/home/data/agentmatrix_run
echo "=== 文件单（前 3 行）+ 条数 ==="
head -3 "$RUN/delivery/live_signals/file_orders.csv" 2>/dev/null | sed 's/^/  /'
echo "  条数: $(($(wc -l < "$RUN/delivery/live_signals/file_orders.csv") - 1))"
echo
echo "=== 条件单 / Supabase 行 ==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import json
base = "/home/data/agentmatrix_run/delivery/live_signals/"
for name in ("conditional_orders.json", "supabase_rows.json"):
    try:
        d = json.load(open(base + name))
        items = d if isinstance(d, list) else d.get("orders") or d.get("rows") or []
        pushed = sum(1 for r in items if isinstance(r, dict) and r.get("pushed") is True)
        print("  %-26s 条数=%d  pushed=true 的条数=%d" % (name, len(items), pushed))
        if items:
            print("     样例:", json.dumps(items[0], ensure_ascii=False)[:180])
    except Exception as e:
        print("  %s 读取失败: %s" % (name, e))
PYEOF
echo
echo "=== 交付目录 ==="
ls -la "$RUN/delivery" 2>/dev/null | sed 's/^/  /'
echo
echo "=== README 头部（生成的说明）==="
head -12 "$RUN/delivery/README.md" 2>/dev/null | sed 's/^/  /'
echo
echo "=== 补充层 ==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 -c "
import json
d = json.load(open('/home/data/agentmatrix_run/delivery/supplementary_report.json'))
print('  FDR:', json.dumps(d.get('summary'), ensure_ascii=False))
print('  边际:', json.dumps(d.get('marginal_effect'), ensure_ascii=False)[:160])
"
echo
echo "=== 资源与守护终态 ==="
echo "  磁盘可用: $(df -h / | awk 'NR==2{print $4}')"
echo "  内存可用: $(free -g | awk '/^Mem:/{print $7}')GB"
echo "  仍在跑: $(ps -eo args | awk '/retain_passing|mirror_runtime|pool_watchdog|auto_deliver|run_pool/ && !/awk/ {c++} END {print c+0}') 个（交付后 pool/watchdog/auto_deliver 应已退出，只剩 retain/mirror）"
ps -eo etime,args | awk '/retain_passing|mirror_runtime|pool_watchdog|auto_deliver|run_pool/ && !/awk/ {print "    " $1, substr($0, index($0,$2), 70)}'
date -Is
