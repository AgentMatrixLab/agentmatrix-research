RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
REH=$RUN/rehearsal
cat > "$REH/run_neworder.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
PANEL=$RUN/panel/validation_panel.parquet
RUNS=$RUN/runtime_mirror/data/factor_lab/validation_runs
REH=$RUN/rehearsal
cd "$REPO" || exit 1
export PYTHONPATH=$REPO

echo "########## 4a. 策略演示（发布聚类）$(date -Is) ##########"
/usr/bin/time -f "DEMOS wall=%es maxrss=%MkB" \
  "$PY" -X utf8 -u scripts/build_strategy_demos.py \
    --panel-file "$PANEL" --factor-file "$REH/factor_values.parquet" \
    --runs-dir "$RUNS" --out-dir "$REH/strategy_demos"
echo "DEMOS exit=$?"

echo
echo "########## 4b. 交付清单（复用聚类）$(date -Is) ##########"
/usr/bin/time -f "MANIFEST wall=%es maxrss=%MkB" \
  "$PY" -X utf8 -u scripts/build_delivery_manifest.py \
    --candidates "$RUN/candidate_list.csv" \
    --batch-manifest "$REH/merged_oos/batch_manifest.json" \
    --runs-dir "$RUNS" \
    --supplementary "$REH/supplementary_report.json" \
    --factor-file "$REH/factor_values.parquet" \
    --cluster-threshold 0.7 \
    --clusters-json "$REH/strategy_demos/clusters.json" \
    --summary-out "$REH/delivery_manifest.summary.json" \
    --out "$REH/delivery_manifest.csv"
echo "MANIFEST exit=$?"

echo
echo "########## 5. 实盘信号 $(date -Is) ##########"
/usr/bin/time -f "SIGNALS wall=%es maxrss=%MkB" \
  "$PY" -X utf8 -u scripts/build_live_signals.py \
    --panel-file "$PANEL" --factor-file "$REH/factor_values.parquet" \
    --runs-dir "$RUNS" --delivery-manifest "$REH/delivery_manifest.csv" \
    --out-dir "$REH/live_signals"
echo "SIGNALS exit=$?"
echo "########## 完成 $(date -Is) ##########"
EOF
sed -i 's/\r$//' "$REH/run_neworder.sh"
chmod +x "$REH/run_neworder.sh"
rm -f "$REH/strategy_demos/clusters.json"
setsid nohup bash "$REH/run_neworder.sh" > "$REH/run_neworder.log" 2>&1 < /dev/null &
echo "  已启动 pid=$!  （断开 SSH 也不会被杀）"
sleep 15
head -12 "$REH/run_neworder.log"
date -Is
