#!/usr/bin/env bash
# Keep the shard pool running while shards remain, so the critical path does not sit idle
# until someone happens to look.
#
# The run has ~17 unattended hours left. If `run_pool.sh` dies -- which has happened twice in
# this project, once from an external `pkill -f` -- nothing restarts it, and the loss is only
# noticed at the next inspection. This reduces that from hours to minutes.
#
# What it deliberately does NOT do:
#   * it never kills anything (no pkill, no signal), so it cannot repeat the two incidents where
#     a pattern kill took out the caller's own shell;
#   * it does not start a second pool: it requires BOTH no run_pool.sh and no in-flight
#     run_one_shard.sh, and it waits out a cooldown after its own last restart;
#   * it does not restart while the downstream chain is running, because the chain is
#     memory-hungry and the pool is supposed to be stopped for it.
#
# Every decision is appended to a log, so an unattended restart is visible afterwards rather
# than inferred.
#
# Usage: pool_watchdog.sh [--run DIR] [--total 213] [--interval 300] [--cooldown 900]
set -u

RUN=/home/data/agentmatrix_run
REPO_DEFAULT=$RUN/agentmatrix
TOTAL=213
INTERVAL=300
COOLDOWN=900
MAX_RESTARTS=30
STAMP=71760b4138e350338299a6f48f269099ebbfab5c

while [ $# -gt 0 ]; do
  case "$1" in
    --run) RUN="$2"; shift 2 ;;
    --total) TOTAL="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --cooldown) COOLDOWN="$2"; shift 2 ;;
    --stamp) STAMP="$2"; shift 2 ;;
    *) echo "unknown argument: $1"; exit 2 ;;
  esac
done

REPO=$RUN/agentmatrix
LOG=$RUN/logs/pool_watchdog.log
STATE=$RUN/logs/pool_watchdog.state
MARK=mark_watchdog_guard

# Single instance, by an atomic mkdir rather than by pattern-matching `ps`: a `pgrep -f
# pool_watchdog.sh` guard matches the script's own command line, reports "already running", and
# silently never starts -- which is exactly what happened the first time this was launched.
LOCK=$RUN/logs/pool_watchdog.lock
if ! mkdir "$LOCK" 2>/dev/null; then
  holder=$(cat "$LOCK/pid" 2>/dev/null || echo "")
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then
    echo "another watchdog is running (pid $holder); exiting"
    exit 0
  fi
  # The holder is gone: a stale lock from a killed watchdog. Take it over.
  rm -rf "$LOCK"
  mkdir "$LOCK" 2>/dev/null || { echo "could not acquire the watchdog lock"; exit 1; }
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT INT TERM

log() { echo "$(date -Is)  $*" >> "$LOG"; }

completed() { ls "$RUN"/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l; }
pool_running() {
  ps -eo args | awk -v m="$MARK" '$0 !~ m && /run_pool\.sh/ {c++} END {print c+0}'
}
shard_running() {
  ps -eo args | awk -v m="$MARK" '$0 !~ m && /run_one_shard\.sh [0-9]/ {c++} END {print c+0}'
}
chain_running() {
  ps -eo args | awk -v m="$MARK" '$0 !~ m && /run_downstream\.sh/ {c++} END {print c+0}'
}

restarts=0
[ -f "$STATE" ] && restarts=$(cat "$STATE" 2>/dev/null || echo 0)
last_restart=0

log "watchdog start: total=$TOTAL interval=${INTERVAL}s cooldown=${COOLDOWN}s stamp=$STAMP restarts_so_far=$restarts"

while true; do
  done_n=$(completed)
  if [ "$done_n" -ge "$TOTAL" ]; then
    log "all $TOTAL shards complete; watchdog exiting"
    exit 0
  fi

  if [ "$(pool_running)" -gt 0 ]; then
    sleep "$INTERVAL"
    continue
  fi

  if [ "$(chain_running)" -gt 0 ]; then
    log "pool absent but the downstream chain is running; leaving it alone"
    sleep "$INTERVAL"
    continue
  fi

  inflight=$(shard_running)
  if [ "$inflight" -gt 0 ]; then
    # Workers alive without a parent pool: a pool mid-teardown, or orphans finishing a phase.
    # Waiting avoids starting a competing pool against them.
    log "no pool but $inflight shard worker(s) still alive; waiting rather than racing them"
    sleep "$INTERVAL"
    continue
  fi

  now=$(date +%s)
  since=$((now - last_restart))
  if [ "$last_restart" -ne 0 ] && [ "$since" -lt "$COOLDOWN" ]; then
    log "pool down but within cooldown (${since}s < ${COOLDOWN}s); waiting"
    sleep "$INTERVAL"
    continue
  fi

  if [ "$restarts" -ge "$MAX_RESTARTS" ]; then
    log "restart cap ($MAX_RESTARTS) reached; refusing to restart again. Needs a human."
    exit 1
  fi

  log "pool is down with $done_n/$TOTAL shards done -- restarting with pinned stamp"
  cd "$REPO" || { log "repo missing at $REPO"; exit 1; }
  sed -i 's/\r$//' scripts/dev/run_pool.sh scripts/dev/run_one_shard.sh 2>/dev/null
  setsid nohup env AGENTMATRIX_COMMIT="$STAMP" bash "$REPO/scripts/dev/run_pool.sh" "$TOTAL" 2 \
    >> "$RUN/logs/pool_run_watchdog.log" 2>&1 < /dev/null &
  sleep 30
  restarts=$((restarts + 1))
  last_restart=$(date +%s)
  echo "$restarts" > "$STATE"
  log "restart #$restarts issued; now running=$(pool_running) workers=$(shard_running)"

  sleep "$INTERVAL"
done
