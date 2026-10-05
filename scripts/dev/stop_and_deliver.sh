#!/usr/bin/env bash
# Stop the shard run safely and produce the delivery, in one auditable step.
#
# The hand-off is the moment where a slip is most expensive: killing the pool with `pkill -f`
# has already killed a caller's own shell twice in this project, and `rm -rf shards` destroyed
# half an hour of finished work once. This script does the safe version of each.
#
#   1. report what exists, and refuse to continue if the evidence is incomplete
#   2. optionally wait for the two in-flight shards to finish rather than discarding them
#   3. stop the pool by PROCESS GROUP, never by pattern
#   4. run the downstream chain
#   5. print the delivered count
#
# Usage:  stop_and_deliver.sh [--wait-minutes N] [--run /home/data/agentmatrix_run]
set -u

RUN=/home/data/agentmatrix_run
WAIT_MINUTES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --wait-minutes) WAIT_MINUTES="$2"; shift 2 ;;
    --run) RUN="$2"; shift 2 ;;
    *) echo "unknown argument: $1"; exit 2 ;;
  esac
done

REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
MARK=mark_stop_deliver_guard
OOS_OK=$(ls "$RUN"/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)
PARTS_N=$(ls "$RUN"/delivery/values/parts/*.parquet 2>/dev/null | wc -l)

echo "=== 1. 前置检查 ==="
echo "  已完成分片 : $OOS_OK"
echo "  留存 parts : $PARTS_N"
echo "  镜像 runs  : $(ls -d $RUN/runtime_mirror/data/factor_lab/validation_runs/*/ 2>/dev/null | wc -l)"
echo "  磁盘可用   : $(df -h / | awk 'NR==2{print $4}')"
echo "  内存可用   : $(free -g | awk '/^Mem:/{print $7}')GB"
if [ "$OOS_OK" -eq 0 ]; then
  echo "  没有任何分片结果，拒绝交付"
  exit 1
fi
if [ ! -d "$RUN/runtime_mirror/data/factor_lab/validation_runs" ]; then
  echo "  证据镜像不存在；先跑 scripts/dev/recon/70_deploy_mirror.sh"
  exit 1
fi
# The downstream chain is memory-hungry (panel + a 450-column block); it must not run while
# two shard workers are holding their peaks.
RUNNING=$(ps -eo args | awk -v m="$MARK" '$0 !~ m && /run_one_shard\.sh [0-9]/ {c++} END {print c+0}')
echo "  在跑分片   : $RUNNING"

if [ "$WAIT_MINUTES" -gt 0 ] && [ "$RUNNING" -gt 0 ]; then
  echo
  echo "=== 2. 等在跑分片结束（最多 $WAIT_MINUTES 分钟）==="
  waited=0
  while [ "$waited" -lt $((WAIT_MINUTES * 60)) ]; do
    LEFT=$(ps -eo args | awk -v m="$MARK" '$0 !~ m && /run_one_shard\.sh [0-9]/ {c++} END {print c+0}')
    NOW=$(ls "$RUN"/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)
    if [ "$LEFT" -eq 0 ]; then
      echo "  在跑分片已全部结束，完成数 $NOW"
      break
    fi
    sleep 30
    waited=$((waited + 30))
    printf "  等待中 %4ds / %ds，在跑 %s，完成 %s\n" "$waited" $((WAIT_MINUTES * 60)) "$LEFT" "$NOW"
  done
fi

echo
echo "=== 3. 停止 pool（按进程组）==="
POOL_PID=$(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /run_pool\.sh/ {print $1; exit}')
if [ -z "$POOL_PID" ]; then
  echo "  没有找到 run_pool.sh（可能已结束）"
else
  PGID=$(ps -o pgid= -p "$POOL_PID" | tr -d ' ')
  MYPGID=$(ps -o pgid= -p $$ | tr -d ' ')
  echo "  pool pid=$POOL_PID pgid=$PGID 本shell pgid=$MYPGID"
  if [ "$PGID" = "$MYPGID" ]; then
    echo "  中止：pool 与本 shell 同进程组，不敢按组杀"
    exit 1
  fi
  kill -TERM -"$PGID" 2>/dev/null
  sleep 10
  LEFT=$(ps -eo pid,pgid,args | awk -v p="$PGID" -v m="$MARK" '$0 !~ m && $2 == p {c++} END {print c+0}')
  if [ "$LEFT" -gt 0 ]; then
    echo "  仍有 $LEFT 个残留，补 SIGKILL"
    kill -KILL -"$PGID" 2>/dev/null
    sleep 5
  fi
fi
# A shard killed mid-flight leaves no oos manifest, so run_pool.sh would re-queue it later.
# Report that rather than pretending the batch is complete.
STILL_MISSING=$(ls -d "$RUN"/shards/shard* 2>/dev/null | wc -l)
echo "  分片目录 $STILL_MISSING 个，其中完成 $OOS_OK 个（未完成的会在下次 run_pool.sh 时重排）"

echo
echo "=== 4. 下游全链 ==="
cd "$REPO" || exit 1
export PYTHONPATH="$REPO"
sed -i 's/\r$//' scripts/dev/run_downstream.sh
bash scripts/dev/run_downstream.sh "$RUN"
STATUS=$?

echo
echo "=== 5. 结果 ==="
if [ -f "$RUN/delivery/delivery_manifest.csv" ]; then
  "$PY" -X utf8 - "$RUN/delivery/delivery_manifest.csv" <<'PYEOF'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")))
inside = [r for r in rows if r["in_delivery_package"] == "true"]
print(f"  交付清单总行数     : {len(rows)}")
print(f"  IN DELIVERY PACKAGE: {len(inside)}")
print(f"  达成 300 目标      : {'YES' if len(inside) >= 300 else 'NO'}")
PYEOF
fi
if [ -f "$RUN/delivery/cross_check.json" ]; then
  "$PY" -X utf8 - "$RUN/delivery/cross_check.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
print(f"  交叉验证发现数     : {d.get('finding_count')}")
PYEOF
fi
echo "  链退出码: $STATUS"
exit $STATUS
