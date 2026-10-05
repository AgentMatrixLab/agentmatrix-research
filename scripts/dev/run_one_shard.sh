#!/usr/bin/env bash
# Validate exactly one shard: build its factor values, run train and oos, delete the
# factor file. Designed to be invoked by `xargs -P`, one process per shard.
#
# The previous driver used a `wait -n` loop that in practice ran one shard at a
# time -- measured 18 minutes per completed shard with only a single worker alive,
# which put the full run at 37 hours. `xargs -P` is a plain, well-understood worker
# pool and does not depend on how a given bash treats `wait -n` after subshell
# functions.
#
# Usage:  run_one_shard.sh <index>
set -u

RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
PANEL=$RUN/panel/validation_panel.parquet
CONFIG=$REPO/configs/validation_gates.yaml
INDEX="$1"
TAG=$(printf "shard%03d" "$INDEX")
DIR="$RUN/shards/$TAG"
LOG="$RUN/logs/$TAG.log"
EMIT_START=${EMIT_START:-2020-01-02}
MIN_FREE_GB=${MIN_FREE_GB:-10}

mkdir -p "$DIR"

wait_for_memory() {
  local waited=0
  while [ "$(free -g | awk '/^Mem:/{print $7}')" -lt "$MIN_FREE_GB" ]; do
    [ "$waited" -ge 1800 ] && { echo "  memory still tight after 30 min; proceeding"; return 0; }
    sleep 20
    waited=$((waited + 20))
  done
}

{
  echo "### $TAG start $(date -Is)"
  cd "$REPO" || exit 1
  export PYTHONPATH="$REPO"

  echo "--- build ---"
  /usr/bin/time -f "build wall=%es maxrss=%MkB" \
    "$PY" -X utf8 -u scripts/build_factor_values.py \
      --candidates "$DIR/candidate_list.csv" \
      --panel-file "$PANEL" \
      --config "$CONFIG" \
      --output "$DIR/factor_values.parquet" \
      --report "$DIR/build_report.json" \
      --emit-start "$EMIT_START" || { echo "BUILD FAILED"; exit 1; }

  echo "--- train ---"
  wait_for_memory
  /usr/bin/time -f "train wall=%es maxrss=%MkB" \
    "$PY" -X utf8 -u -m research_core.factor_lab.cli validate-batch \
      --candidates "$DIR/candidate_list.csv" \
      --config "$CONFIG" \
      --panel-file "$PANEL" \
      --factor-file "$DIR/factor_values.parquet" \
      --segment train \
      --output-dir "$DIR/train" || echo "TRAIN FAILED"

  echo "--- oos ---"
  wait_for_memory
  /usr/bin/time -f "oos wall=%es maxrss=%MkB" \
    "$PY" -X utf8 -u -m research_core.factor_lab.cli validate-batch \
      --candidates "$DIR/candidate_list.csv" \
      --config "$CONFIG" \
      --panel-file "$PANEL" \
      --factor-file "$DIR/factor_values.parquet" \
      --segment oos \
      --output-dir "$DIR/oos" || echo "OOS FAILED"

  echo "--- release ---"
  rm -f "$DIR/factor_values.parquet"
  echo "### $TAG done $(date -Is)"
} > "$LOG" 2>&1
