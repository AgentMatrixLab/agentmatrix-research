#!/usr/bin/env bash
# Sharded full validation run on the 115 server.
#
# Why sharded: on the real 9,444,457-row panel one candidate costs roughly 40-60
# seconds end to end (base expression plus both perturbation variants). 849 of
# them would also need about 183 GB of factor values against 139 GB free, so the
# run has to be both parallel and self-cleaning. Each shard builds its own factor
# values, runs train and oos validation, keeps only the small results, and deletes
# the multi-GB factor file. Peak disk is one shard, not the whole run.
#
# Wave size is a parameter because it has to come from measured RSS (~8.5 GB per
# worker with column pruning), not from nproc.
#
# Usage:  run_sharded.sh <shards> <parallel>
set -u

RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
PANEL=$RUN/panel/validation_panel.parquet
CONFIG=$REPO/configs/validation_gates.yaml
SHARDS=${1:-16}
PARALLEL=${2:-4}
LOGS=$RUN/logs

mkdir -p "$LOGS" "$RUN/shards"

cd "$REPO" || exit 1
export PYTHONPATH="$REPO"

echo "=== splitting into $SHARDS shards ==="
"$PY" -X utf8 - "$SHARDS" <<'PYEOF'
import csv, os, sys
shards = int(sys.argv[1])
run = "/home/data/agentmatrix_run"
rows = list(csv.DictReader(open(run + "/candidate_list.csv", encoding="utf-8")))
buckets = [[] for _ in range(shards)]
for index, row in enumerate(rows):
    buckets[index % shards].append(row)
fields = list(rows[0])
for index, bucket in enumerate(buckets):
    target = run + "/shards/shard%02d" % index
    os.makedirs(target, exist_ok=True)
    with open(target + "/candidate_list.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(bucket)
    families = sorted({r["factor_id"].split(":")[0] for r in bucket})
    print("  shard%02d: %d factors  families=%s" % (index, len(bucket), ",".join(families)))
PYEOF

run_shard() {
  local index="$1"
  local tag
  tag=$(printf "shard%02d" "$index")
  local dir="$RUN/shards/$tag"
  local log="$LOGS/$tag.log"
  {
    echo "### $tag start $(date -Is)"
    echo "--- build factor values ---"
    /usr/bin/time -f "build wall=%es maxrss=%MkB" \
      "$PY" -X utf8 -u scripts/build_factor_values.py \
        --candidates "$dir/candidate_list.csv" \
        --panel-file "$PANEL" \
        --config "$CONFIG" \
        --output "$dir/factor_values.parquet" \
        --report "$dir/build_report.json" || { echo "BUILD FAILED"; return 1; }

    echo "--- validate train ---"
    /usr/bin/time -f "train wall=%es maxrss=%MkB" \
      "$PY" -X utf8 -u -m research_core.factor_lab.cli validate-batch \
        --candidates "$dir/candidate_list.csv" \
        --config "$CONFIG" \
        --panel-file "$PANEL" \
        --factor-file "$dir/factor_values.parquet" \
        --segment train \
        --output-dir "$dir/train" || { echo "TRAIN FAILED"; return 1; }

    echo "--- validate oos ---"
    /usr/bin/time -f "oos wall=%es maxrss=%MkB" \
      "$PY" -X utf8 -u -m research_core.factor_lab.cli validate-batch \
        --candidates "$dir/candidate_list.csv" \
        --config "$CONFIG" \
        --panel-file "$PANEL" \
        --factor-file "$dir/factor_values.parquet" \
        --segment oos \
        --output-dir "$dir/oos" || { echo "OOS FAILED"; return 1; }

    echo "--- release factor file ---"
    du -sh "$dir/factor_values.parquet" 2>/dev/null
    rm -f "$dir/factor_values.parquet"
    echo "### $tag done $(date -Is)"
  } > "$log" 2>&1
}

echo
echo "=== running: $SHARDS shards, $PARALLEL at a time ==="
START=$(date +%s)
RUNNING=0
for i in $(seq 0 $((SHARDS - 1))); do
  run_shard "$i" &
  RUNNING=$((RUNNING + 1))
  if [ "$RUNNING" -ge "$PARALLEL" ]; then
    wait -n 2>/dev/null || wait
    RUNNING=$((RUNNING - 1))
  fi
  MEMFREE=$(free -g | awk '/^Mem:/{print $7}')
  DISKFREE=$(df -h / | awk 'NR==2{print $4}')
  echo "  started $((i + 1))/$SHARDS  memfree=${MEMFREE}GB  diskfree=${DISKFREE}"
done
wait
END=$(date +%s)
echo
echo "=== all done in $(( (END - START) / 60 )) minutes ==="
