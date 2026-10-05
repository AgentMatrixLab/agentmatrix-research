RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
THRESHOLD=308
TOTAL=213

echo "════════ 交付状态 $(date '+%m-%d %H:%M') ════════"

echo
echo "▌分片作业"
DONE=$(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)
PARTS=$(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)
PASS=$($PY -X utf8 - "$RUN" <<'PYEOF'
import glob, json, sys
total = 0
for path in glob.glob(f"{sys.argv[1]}/shards/shard*/oos/batch_manifest.json"):
    try:
        payload = json.load(open(path))
    except Exception:
        continue
    total += sum(1 for r in payload.get("results", [])
                 if r.get("status") == "validated" and not r.get("failed_gates"))
print(total)
PYEOF
)
echo "  完成 $DONE/$TOTAL 片   留存 parts $PARTS   通过 $PASS 个"
if [ "$DONE" -gt 0 ]; then
  echo "  过闸率 $(awk -v p="$PASS" -v d="$DONE" 'BEGIN{printf "%.1f%%", 100*p/(4*d)}')"
fi
NEED=$((THRESHOLD - PASS))
if [ "$NEED" -le 0 ]; then
  echo "  ⇒ 已达阈值 $THRESHOLD，自动交付应已/即将触发"
else
  SHARDS=$(awk -v n="$NEED" -v p="$PASS" -v d="$DONE" 'BEGIN{printf "%.0f", n*(4*d)/p/4}')
  HOURS=$(awk -v s="$SHARDS" 'BEGIN{printf "%.1f", s/6.4}')
  echo "  ⇒ 距阈值 $THRESHOLD 还差 $NEED 个 ≈ $SHARDS 片 ≈ $HOURS 小时"
fi
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {printf "  在跑: arg=%s etime=%s\n", $NF, $2}'

echo
echo "▌守护进程"
for pat in "mirror_runtime_data" "retain_passing_values" "run_pool.sh" "pool_watchdog.sh --run" "auto_deliver.sh --run"; do
  n=$(ps -eo args | awk -v p="$pat" 'index($0,p)>0 && !/awk/ {c++} END {print c+0}')
  case "$pat" in
    "run_pool.sh") [ "$n" = "1" ] && s="OK" || s="** 异常 **" ;;
    *) [ "$n" = "1" ] && s="OK" || s="** 异常（$n）**" ;;
  esac
  printf "  %-28s %s\n" "$pat" "$s"
done

echo
echo "▌自动交付"
if [ -f "$RUN/logs/auto_deliver.done" ]; then
  echo "  ** 已触发 ** $(cat $RUN/logs/auto_deliver.done)"
  [ -f "$RUN/logs/auto_deliver_acceptance.log" ] && tail -4 "$RUN/logs/auto_deliver_acceptance.log" | sed 's/^/    /'
else
  echo "  未触发（等待阈值或截止）"
  tail -2 "$RUN/logs/auto_deliver.log" 2>/dev/null | sed 's/^/    /'
fi

echo
echo "▌资源"
df -h / | awk 'NR==2{printf "  磁盘可用 %s / %s\n", $4, $2}'
free -g | awk '/^Mem:/{printf "  内存可用 %sGB / %sGB\n", $7, $2}'

echo
echo "▌交付产物（若已产出）"
if [ -f "$RUN/delivery/delivery_manifest.summary.json" ]; then
  $PY -X utf8 -c "
import json
s = json.load(open('$RUN/delivery/delivery_manifest.summary.json'))
print('  in_delivery_package =', s.get('in_delivery_package'), '/ 目标 300')
print('  validated =', s.get('validated'), ' fdr_accepted =', s.get('fdr_accepted'))
" 2>/dev/null || echo "  读取失败"
else
  echo "  尚无交付清单"
fi
echo "════════════════════════════════════════"
