#!/usr/bin/env bash
# Resume after the 115 box is restarted.
#
# Deliberately verifies before it launches anything: three runs have already died
# to OOM, so the loader fix is measured on a tiny sample first rather than assumed
# across a multi-hour job.
#
# Usage:  resume_after_reboot.sh
set -u

RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python

echo "########## 0. 机器状态 ##########"
uptime
free -g | head -2
df -h / | tail -1

echo
echo "########## 1. 关键产物是否还在（重启不应丢失） ##########"
for f in "$RUN/panel/validation_panel.parquet" \
         "$RUN/panel/validation_panel.parquet.json" \
         "$RUN/candidate_list.csv" \
         "$REPO/configs/validation_gates.yaml" \
         "$REPO/scripts/build_factor_values.py"; do
  if [ -f "$f" ]; then
    printf "  OK   %-60s %s\n" "$f" "$(stat -c %s "$f")"
  else
    printf "  MISS %s\n" "$f"
  fi
done

echo
echo "########## 2. 清掉上一轮的残留 ##########"
for pid in $(ps -eo pid,args | grep -E "[b]uild_factor_values.py|[v]alidate-batch|[r]un_sharded.sh" | awk '{print $1}'); do
  echo "  killing $pid"
  kill -KILL "$pid" 2>/dev/null
done
sleep 2
BEFORE=$(df -h / | awk 'NR==2{print $4}')
rm -rf "$RUN"/shards "$RUN"/memtest "$RUN"/tiny "$RUN"/pilot
AFTER=$(df -h / | awk 'NR==2{print $4}')
echo "  磁盘可用: $BEFORE -> $AFTER"
mkdir -p "$RUN/shards" "$RUN/logs"

echo
echo "########## 3. 确认代码是修复后的版本 ##########"
cd "$REPO" || exit 1
export PYTHONPATH="$REPO"
git log --oneline -1 2>/dev/null || echo "  (非 git 目录)"
grep -c "category" research_core/factor_lab/precomputed_factors.py
echo "  ^ 应 > 0，表示加载器的 categorical 修复在位"
grep -c "wait_for_memory" scripts/dev/run_sharded.sh
echo "  ^ 应 > 0，表示内存门控在位"

echo
echo "########## 4. 先量内存（1 分钟）再决定并行度 ##########"
bash scripts/dev/verify_loader_memory.sh 2>&1 | tail -20

echo
echo "########## 5. 下一步 ##########"
cat <<'NOTE'
  若上一步峰值 RSS 明显低于 10 GB：
      bash scripts/dev/run_sharded.sh 54 4 2020-01-02
  若仍然很高（> 20 GB）：
      bash scripts/dev/run_sharded.sh 54 2 2020-01-02
  跑完后再执行：
      bash scripts/dev/run_downstream.sh
NOTE
