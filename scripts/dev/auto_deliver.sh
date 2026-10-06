#!/usr/bin/env bash
# Run the delivery by itself once enough factors have passed the frozen gates.
#
# Everything about the hand-off currently depends on someone being present at the right moment:
# an agent turn, or an inspection. The shard run needs roughly fifteen more hours, and if the
# decision to stop and deliver is missed -- rounds exhausted, session idle, someone asleep --
# the deadline passes with the results sitting on disk. This makes the server do it.
#
# It stops the watchdog FIRST, then the pool, then runs the chain. That order is load-bearing:
# with a working watchdog, stopping the pool first leaves a gap where it sees no pool and no
# chain and starts a new one underneath the delivery, which is the memory contention that killed
# shards 004/005.
#
# It never kills by pattern (no pkill) and never removes shard directories.
#
# Usage: auto_deliver.sh [--run DIR] [--threshold 308] [--interval 300]
set -u

RUN=/home/data/agentmatrix_run
THRESHOLD=308          # passing factors needed before delivering; 300 is the commitment, this
                       # leaves margin for the handful of risk-exposure exclusions
TOTAL=213
INTERVAL=300
STAMP=71760b4138e350338299a6f48f269099ebbfab5c
DRY=0
DEADLINE="2026-10-07 06:00"   # deliver what exists by then even if short: an honest undersized
                              # delivery beats missing the date entirely

while [ $# -gt 0 ]; do
  case "$1" in
    --run) RUN="$2"; shift 2 ;;
    --threshold) THRESHOLD="$2"; shift 2 ;;
    --total) TOTAL="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --deadline) DEADLINE="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) echo "unknown argument: $1"; exit 2 ;;
  esac
done
DEADLINE_EPOCH=$(date -d "$DEADLINE" +%s 2>/dev/null || echo 0)

REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
LOG=$RUN/logs/auto_deliver.log
DONE_MARK=$RUN/logs/auto_deliver.done

log() { echo "$(date -Is)  $*" >> "$LOG"; }

completed() { ls "$RUN"/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l; }

passing() {
  "$PY" -X utf8 - "$RUN" <<'PYEOF'
import glob, json, sys
run = sys.argv[1]
total = 0
for path in glob.glob(f"{run}/shards/shard*/oos/batch_manifest.json"):
    try:
        payload = json.load(open(path))
    except (OSError, json.JSONDecodeError):
        continue
    for result in payload.get("results", []):
        if result.get("status") == "validated" and not result.get("failed_gates"):
            total += 1
print(total)
PYEOF
}

if [ -f "$DONE_MARK" ]; then
  log "delivery already performed ($(cat "$DONE_MARK")); exiting"
  exit 0
fi

log "auto-delivery armed: threshold=${THRESHOLD} passing factors, total=$TOTAL shards"

while true; do
  done_n=$(completed)
  pass_n=$(passing)
  log "status: $done_n/$TOTAL shards complete, $pass_n passing factors"

  NOW_EPOCH=$(date +%s)
  PAST_DEADLINE=0
  if [ "$DEADLINE_EPOCH" -gt 0 ] && [ "$NOW_EPOCH" -ge "$DEADLINE_EPOCH" ]; then
    PAST_DEADLINE=1
  fi

  if [ "$pass_n" -ge "$THRESHOLD" ] || [ "$done_n" -ge "$TOTAL" ] || [ "$PAST_DEADLINE" -eq 1 ]; then
    if [ "$pass_n" -ge "$THRESHOLD" ]; then
      log "threshold reached ($pass_n >= $THRESHOLD) -- proceeding to delivery"
    elif [ "$done_n" -ge "$TOTAL" ]; then
      log "all shards complete with $pass_n passing (< $THRESHOLD); delivering what exists"
    else
      log "deadline ($DEADLINE) reached with $pass_n passing (< $THRESHOLD); delivering what exists"
    fi

    # Retention writes a shard's part a few seconds AFTER its oos manifest appears, so the two
    # counts can disagree by one for a moment. Entering the chain inside that window makes
    # step 2 fall back to rebuilding EVERY passing factor instead of using the parts -- hours of
    # work and a lot of memory, triggered by a timing accident. Wait for them to agree first.
    for _ in $(seq 1 60); do
      OOS_N=$(completed)
      PART_N=$(ls "$RUN"/delivery/values/parts/*.parquet 2>/dev/null | wc -l)
      if [ "$PART_N" -ge "$OOS_N" ]; then
        break
      fi
      log "waiting for retention to catch up: parts=$PART_N oos=$OOS_N"
      sleep 15
    done
    log "retention coverage at chain start: oos=$OOS_N parts=$PART_N"

    # A chain run in progress owns the delivery directory; do not race it.
    CHAIN_N=$(ps -eo args | awk '/run_downstream\.sh/ && !/awk/ {c++} END {print c+0}')
    if [ "$CHAIN_N" -gt 0 ]; then
      log "a chain run is already in progress; waiting"
      sleep "$INTERVAL"
      continue
    fi

    if [ "$DRY" -eq 1 ]; then
      log "DRY RUN: would stop the watchdog, stop the pool, and run the chain now"
      exit 0
    fi

    # 1. watchdog down first
    WDPID=$(cat "$RUN/logs/pool_watchdog.lock/pid" 2>/dev/null || echo "")
    if [ -n "$WDPID" ] && kill -0 "$WDPID" 2>/dev/null; then
      kill -TERM "$WDPID" 2>/dev/null
      for _ in 1 2 3 4 5 6; do kill -0 "$WDPID" 2>/dev/null || break; sleep 2; done
      kill -0 "$WDPID" 2>/dev/null && kill -KILL "$WDPID" 2>/dev/null
      log "watchdog stopped (pid $WDPID)"
    else
      log "no watchdog running"
    fi
    rm -rf "$RUN/logs/pool_watchdog.lock" 2>/dev/null

    # 2. pool down, by process group
    POOL_PID=$(ps -eo pid,args | awk '/run_pool\.sh/ && !/awk/ && !/auto_deliver/ {print $1; exit}')
    if [ -n "$POOL_PID" ]; then
      PGID=$(ps -o pgid= -p "$POOL_PID" | tr -d ' ')
      MYPGID=$(ps -o pgid= -p $$ | tr -d ' ')
      if [ "$PGID" = "$MYPGID" ]; then
        log "ABORT: the pool shares this shell's process group"
        exit 1
      fi
      kill -TERM -"$PGID" 2>/dev/null
      sleep 15
      kill -KILL -"$PGID" 2>/dev/null
      log "pool stopped (pgid $PGID)"
    else
      log "no pool running"
    fi
    sleep 5

    # 3. the chain
    log "starting the downstream chain"
    cd "$REPO" || { log "repo missing"; exit 1; }
    export PYTHONPATH="$REPO"
    sed -i 's/\r$//' scripts/dev/run_downstream.sh
    bash scripts/dev/run_downstream.sh "$RUN" >> "$RUN/logs/auto_deliver_chain.log" 2>&1
    status=$?
    log "chain finished with exit $status"

    # 4. the acceptance verdict, BEFORE the done-marker.
    #
    # The chain reports success when the critical steps succeed; the cross-check and the
    # packaging step are advisory by design, so a chain exit of 0 does NOT mean the artifacts are
    # consistent. Leaving acceptance out of the recorded line would let a future reader treat
    # "chain_exit=0" as "delivered cleanly". So the verdict goes in the same line.
    acceptance="skipped"
    if [ -f "$REPO/scripts/verify_delivery.py" ]; then
      "$PY" -X utf8 "$REPO/scripts/verify_delivery.py" --delivery-dir "$RUN/delivery" \
        >> "$RUN/logs/auto_deliver_acceptance.log" 2>&1
      acceptance=$?
      log "acceptance check exit $acceptance; see logs/auto_deliver_acceptance.log"
    fi

    if [ -f "$RUN/delivery/delivery_manifest.summary.json" ]; then
      delivered=$("$PY" -X utf8 -c "
import json
print(json.load(open('$RUN/delivery/delivery_manifest.summary.json')).get('in_delivery_package'))
" 2>/dev/null || echo "?")
      log "delivered factors in package: $delivered"
      echo "$(date -Is) chain_exit=$status acceptance_exit=$acceptance in_delivery_package=$delivered" > "$DONE_MARK"
    else
      log "no delivery manifest was produced"
      echo "$(date -Is) chain_exit=$status acceptance_exit=$acceptance no_manifest" > "$DONE_MARK"
    fi

    # Leave the pool stopped: the run is over, and a restart would only add load.
    exit "$status"
  fi

  sleep "$INTERVAL"
done
