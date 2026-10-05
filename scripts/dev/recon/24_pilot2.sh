cd /home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
RUN=/home/data/agentmatrix_run
export PYTHONPATH=$RUN/agentmatrix
mkdir -p $RUN/logs

echo "===== 构建 8 因子分层抽样清单 ====="
$PY -X utf8 - <<'EOF'
import csv, sys
rows = list(csv.DictReader(open("/home/data/agentmatrix_run/candidate_list.csv", encoding="utf-8")))
by_family = {}
for r in rows:
    by_family.setdefault(r["factor_id"].split(":")[0], []).append(r)
sample = []
for fam in sorted(by_family):
    sample.append(by_family[fam][len(by_family[fam]) // 2])
    if len(sample) >= 8:
        break
with open("/home/data/agentmatrix_run/pilot_candidates.csv", "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(sample)
print("  " + ", ".join(s["factor_id"] for s in sample))
EOF

echo
echo "===== build_factor_values（后台 + 日志） ====="
nohup /usr/bin/time -v $PY -X utf8 scripts/build_factor_values.py \
    --candidates $RUN/pilot_candidates.csv \
    --panel-file $RUN/panel/validation_panel.parquet \
    --config configs/validation_gates.yaml \
    --output $RUN/pilot/factor_values.parquet \
    --report $RUN/pilot/report.json \
    > $RUN/logs/pilot_build.log 2>&1 &
BUILD_PID=$!
echo "  pid=$BUILD_PID  日志: $RUN/logs/pilot_build.log"

# 每 30 秒报一次内存与进度，最多 40 分钟
for i in $(seq 1 80); do
  sleep 30
  if ! kill -0 $BUILD_PID 2>/dev/null; then
    echo "  进程结束于第 $((i*30)) 秒"
    break
  fi
  RSS=$(ps -o rss= -p $BUILD_PID 2>/dev/null | awk '{printf "%.1f", $1/1048576}')
  LAST=$(tail -1 $RUN/logs/pilot_build.log 2>/dev/null | tr -d '\r' | cut -c1-90)
  echo "  [$((i*30))s] RSS=${RSS}GB | $LAST"
done

echo
echo "===== 结果 ====="
tail -25 $RUN/logs/pilot_build.log
echo
grep -E "Elapsed \(wall|Maximum resident" $RUN/logs/pilot_build.log
echo
ls -la $RUN/pilot/ 2>/dev/null
echo
echo "===== 剩余磁盘 ====="
df -h / | tail -1
