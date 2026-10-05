RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
PANEL=$RUN/panel/validation_panel.parquet
RUNS=$RUN/runtime_mirror/data/factor_lab/validation_runs
REH=$RUN/rehearsal
cd "$REPO" || exit 1
export PYTHONPATH=$REPO

echo "=== 确认修复已到位 ==="
grep -c 'missing_price_policy="last_close"' scripts/build_strategy_demos.py
grep -c 'equal_weighted' scripts/build_strategy_demos.py
ls -la scripts/build_live_signals.py

echo
echo "=== 远程侧启动（setsid，断开 SSH 也不会被杀）==="
cat > "$REH/run_5ab.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
PANEL=$RUN/panel/validation_panel.parquet
RUNS=$RUN/runtime_mirror/data/factor_lab/validation_runs
REH=$RUN/rehearsal
cd "$REPO" || exit 1
export PYTHONPATH=$REPO
echo "########## 5a. 策略演示 $(date -Is) ##########"
/usr/bin/time -f "DEMOS wall=%es maxrss=%MkB" \
  "$PY" -X utf8 -u scripts/build_strategy_demos.py \
    --panel-file "$PANEL" \
    --factor-file "$REH/factor_values.parquet" \
    --runs-dir "$RUNS" \
    --out-dir "$REH/strategy_demos"
echo "DEMOS exit=$?"
echo
echo "########## 5b. 实盘信号 $(date -Is) ##########"
/usr/bin/time -f "SIGNALS wall=%es maxrss=%MkB" \
  "$PY" -X utf8 -u scripts/build_live_signals.py \
    --panel-file "$PANEL" \
    --factor-file "$REH/factor_values.parquet" \
    --runs-dir "$RUNS" \
    --delivery-manifest "$REH/delivery_manifest.csv" \
    --out-dir "$REH/live_signals"
echo "SIGNALS exit=$?"
echo "########## 5ab 完成 $(date -Is) ##########"
EOF
sed -i 's/\r$//' "$REH/run_5ab.sh"
chmod +x "$REH/run_5ab.sh"
rm -rf "$REH/live_signals"
setsid nohup bash "$REH/run_5ab.sh" > "$REH/run_5ab.log" 2>&1 < /dev/null &
echo "  已启动 pid=$!"
sleep 20
echo "--- 日志开头 ---"
head -20 "$REH/run_5ab.log"
date -Is
