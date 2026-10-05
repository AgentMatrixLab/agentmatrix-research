RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/parallel_build.log
cat > "$RUN/rehearsal/parallel_build.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
W=$RUN/rehearsal/parallel
rm -rf "$W"; mkdir -p "$W"
cd $REPO || exit 1
export PYTHONPATH=$REPO
PANEL=$RUN/panel/validation_panel.parquet
CONFIG=$REPO/configs/validation_gates.yaml
echo "start $(date -Is)  nproc=$(nproc)"

echo
echo "########## 1. 等价性：便宜分片（shard022）jobs=1 vs jobs=4 ##########"
for j in 1 4; do
  /usr/bin/time -f "  jobs=$j wall=%es maxrss=%MkB" \
    $PY -X utf8 -u scripts/build_factor_values.py \
      --candidates $RUN/shards/shard022/candidate_list.csv \
      --panel-file "$PANEL" --config "$CONFIG" \
      --output "$W/c022_j$j.parquet" --report "$W/c022_j$j.report.json" \
      --emit-start 2020-01-02 2>&1 | grep -E 'wall=|s/factor|FAILURES' | sed 's/^/    /'
done
echo "  --- sha256 对比 ---"
sha256sum "$W/c022_j1.parquet" "$W/c022_j4.parquet" | sed 's/^/    /'
if [ "$(sha256sum < "$W/c022_j1.parquet")" = "$(sha256sum < "$W/c022_j4.parquet")" ]; then
  echo "    BYTE-IDENTICAL: YES"
else
  echo "    BYTE-IDENTICAL: NO  <<< 不得启用并行"
fi
echo "  --- report 对比 ---"
$PY -X utf8 - "$W" <<'PYEOF'
import json, sys
w = sys.argv[1]
a = json.load(open(f"{w}/c022_j1.report.json"))
b = json.load(open(f"{w}/c022_j4.report.json"))
keys = ("base_factors", "series", "rows", "vacuous_perturbation",
        "ambiguous_window_substitutions", "failures")
same = all(a[k] == b[k] for k in keys)
print("    report 关键字段一致:", same)
for k in keys:
    if a[k] != b[k]:
        print("      差异", k, a[k], "!=", b[k])
PYEOF

echo
echo "########## 2. 提速：昂贵分片（shard023）jobs=4（串行基线为日志实测 1851s）##########"
/usr/bin/time -f "  shard023 jobs=4 wall=%es maxrss=%MkB" \
  $PY -X utf8 -u scripts/build_factor_values.py \
    --candidates $RUN/shards/shard023/candidate_list.csv \
    --panel-file "$PANEL" --config "$CONFIG" \
    --output "$W/c023_j4.parquet" --report "$W/c023_j4.report.json" \
    --emit-start 2020-01-02 2>&1 | grep -E 'wall=|s/factor' | sed 's/^/    /'
echo "  串行基线（日志）: $(grep -o 'build wall=[0-9.]*s' $RUN/logs/shard023.log | head -1)"
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/parallel_build.sh"
chmod +x "$RUN/rehearsal/parallel_build.sh"
setsid nohup bash "$RUN/rehearsal/parallel_build.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）"
date -Is
