RUN=/home/data/agentmatrix_run
MARK=mark_9b12_ooswatch

echo "=== 采样 8 分钟：统计同时处于 oos 阶段的 validate-batch 进程数 ==="
echo "  （修复目标是 max <= 1；修复前应为 2）"
max=0
i=0
while [ $i -lt 24 ]; do
  n=$(ps -eo args | awk -v m="$MARK" '$0 !~ m && /validate-batch/ && /--segment oos/ {c++} END {print c+0}')
  t=$(ps -eo args | awk -v m="$MARK" '$0 !~ m && /validate-batch/ && /--segment train/ {c++} END {print c+0}')
  b=$(ps -eo args | awk -v m="$MARK" '$0 !~ m && /build_factor_values/ {c++} END {print c+0}')
  [ "$n" -gt "$max" ] && max=$n
  printf "  t=%02d  oos=%s train=%s build=%s  avail=%sGB\n" "$i" "$n" "$t" "$b" "$(free -g | awk '/^Mem:/{print $7}')"
  i=$((i + 1))
  sleep 20
done
echo
echo "  采样期间同时 oos 的最大进程数: $max  （期望 1）"

echo
echo "=== oos 锁文件状态 ==="
ls -la "$RUN/logs/oos.lock" 2>/dev/null
echo
echo "=== 分片完成情况 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, os, json
run = "/home/data/agentmatrix_run"
done = sorted(os.path.basename(os.path.dirname(os.path.dirname(p)))
              for p in glob.glob(run + "/shards/shard*/oos/batch_manifest.json"))
print("  已完成:", " ".join(done))
total = 0
passed = 0
for p in glob.glob(run + "/shards/shard*/oos/batch_manifest.json"):
    pl = json.load(open(p))
    for r in pl.get("results", []):
        total += 1
        if r.get("status") == "validated" and not r.get("failed_gates"):
            passed += 1
print("  累计因子结果: %d   通过八道门槛: %d   (%.1f%%)" % (total, passed, 100.0 * passed / max(total, 1)))
PYEOF
echo "  parts: $(ls $RUN/delivery/values/parts/*.parquet 2>/dev/null | wc -l)"
echo "  磁盘可用: $(df -h / | awk 'NR==2{print $4}')"
date -Is
