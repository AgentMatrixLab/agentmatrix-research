RUN=/home/data/agentmatrix_run
MARK=mark_pb_guard
echo "=== 停掉未带 --jobs 的那次彩排（只匹配 rehearsal/parallel，绝不碰 pool 的分片）==="
PIDS=$(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /rehearsal\/parallel/ {print $1}')
echo "  待停 PID: ${PIDS:-无}"
for p in $PIDS; do kill -TERM "$p" 2>/dev/null; done
sleep 3
LEFT=$(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /rehearsal\/parallel/ {c++} END {print c+0}')
[ "$LEFT" -gt 0 ] && for p in $(ps -eo pid,args | awk -v m="$MARK" '$0 !~ m && /rehearsal\/parallel/ {print $1}'); do kill -KILL "$p" 2>/dev/null; done
sleep 2
echo "  剩余: $(ps -eo args | awk -v m="$MARK" '$0 !~ m && /rehearsal\/parallel/ {c++} END {print c+0}')"
echo "  pool 的分片进程未受影响:"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "    " $1, $2, $NF}'

echo
echo "=== 重新运行：这次真的带上 --jobs ==="
cat > "$RUN/rehearsal/parallel_build2.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
W=$RUN/rehearsal/parallel2
rm -rf "$W"; mkdir -p "$W"
cd $REPO || exit 1
export PYTHONPATH=$REPO
PANEL=$RUN/panel/validation_panel.parquet
CONFIG=$REPO/configs/validation_gates.yaml
echo "start $(date -Is)  nproc=$(nproc)"
echo
echo "########## 1. 等价性 + 提速：shard022（便宜）##########"
for j in 1 4; do
  /usr/bin/time -f "  jobs=$j wall=%es maxrss=%MkB" \
    $PY -X utf8 -u scripts/build_factor_values.py \
      --candidates $RUN/shards/shard022/candidate_list.csv \
      --panel-file "$PANEL" --config "$CONFIG" \
      --output "$W/c022_j$j.parquet" --report "$W/c022_j$j.report.json" \
      --emit-start 2020-01-02 --jobs "$j" 2>&1 | grep -E 'wall=|s/factor|process' | sed 's/^/    /'
done
echo "  --- sha256 对比（必须相同）---"
A=$(sha256sum < "$W/c022_j1.parquet"); B=$(sha256sum < "$W/c022_j4.parquet")
echo "    jobs=1: $A"
echo "    jobs=4: $B"
[ "$A" = "$B" ] && echo "    BYTE-IDENTICAL: YES" || echo "    BYTE-IDENTICAL: NO  <<< 不得启用"
$PY -X utf8 - "$W" <<'PYEOF'
import json, sys
w = sys.argv[1]
a = json.load(open(f"{w}/c022_j1.report.json")); b = json.load(open(f"{w}/c022_j4.report.json"))
keys = ("base_factors", "series", "rows", "vacuous_perturbation",
        "ambiguous_window_substitutions", "failures")
print("    report 关键字段一致:", all(a[k] == b[k] for k in keys))
PYEOF
echo
echo "########## 2. 昂贵分片 shard023：jobs=1 vs jobs=4 ##########"
for j in 1 4; do
  /usr/bin/time -f "  shard023 jobs=$j wall=%es maxrss=%MkB" \
    $PY -X utf8 -u scripts/build_factor_values.py \
      --candidates $RUN/shards/shard023/candidate_list.csv \
      --panel-file "$PANEL" --config "$CONFIG" \
      --output "$W/c023_j$j.parquet" --report "$W/c023_j$j.report.json" \
      --emit-start 2020-01-02 --jobs "$j" 2>&1 | grep -E 'wall=|s/factor|process' | sed 's/^/    /'
done
echo "  --- sha256 对比（昂贵表达式也必须相同）---"
A=$(sha256sum < "$W/c023_j1.parquet"); B=$(sha256sum < "$W/c023_j4.parquet")
[ "$A" = "$B" ] && echo "    BYTE-IDENTICAL: YES" || echo "    BYTE-IDENTICAL: NO  <<< 不得启用"
echo "  日志里的串行基线: $(grep -o 'build wall=[0-9.]*s' $RUN/logs/shard023.log | head -1)"
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/parallel_build2.sh"
chmod +x "$RUN/rehearsal/parallel_build2.sh"
setsid nohup bash "$RUN/rehearsal/parallel_build2.sh" > "$RUN/rehearsal/parallel_build2.log" 2>&1 < /dev/null &
echo "  已启动（detached，约 40 分钟：含 shard023 串行 1851s 基线）"
date -Is
