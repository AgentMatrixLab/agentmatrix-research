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
#: What counts as "a pool" and "a shard worker". Overridable so the decision logic can be
#: exercised against a stub in a sandbox instead of by killing the real run to see what happens.
POOL_MARKER=run_pool.sh
SHARD_MARKER='run_one_shard\.sh [0-9]'

while [ $# -gt 0 ]; do
  case "$1" in
    --run) RUN="$2"; shift 2 ;;
    --total) TOTAL="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --cooldown) COOLDOWN="$2"; shift 2 ;;
    --stamp) STAMP="$2"; shift 2 ;;
    --pool-marker) POOL_MARKER="$2"; shift 2 ;;
    --shard-marker) SHARD_MARKER="$2"; shift 2 ;;
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
# A trap that cleans up but does NOT exit makes the shell ignore SIGTERM and keep looping --
# which is what happened here: `timeout 60` fired, the lock was removed, and the watchdog
# carried on running for another ten minutes. An unstoppable daemon is a problem in its own
# right: the final hand-off stops the pool before running the chain, and a watchdog that cannot
# be told to stand down would restart the pool underneath it.
release() { rm -rf "$LOCK"; }
on_signal() { release; echo "$(date -Is)  received a stop signal; watchdog exiting" >> "$LOG"; exit 0; }
trap release EXIT
trap on_signal INT TERM

log() { echo "$(date -Is)  $*" >> "$LOG"; }

completed() { ls "$RUN"/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l; }
# Detection must not count the DETECTOR. Two earlier versions got this wrong in ways that made
# the watchdog silently useless -- it started, logged, and slept forever without ever
# restarting anything:
#
#   v1  `pgrep -f pool_watchdog.sh` matched the script's own command line, so it reported
#       "already running" and never started at all.
#   v2  `awk -v pat="$MARKER"` put the marker in the awk process's OWN arguments, so
#       `index($0, pat)` matched the awk line itself and the watchdog concluded a pool was
#       always running. The trace showed `pool_running` returning 1 for a marker that matched
#       nothing on the box.
#
# So the marker travels in the ENVIRONMENT, which `ps -eo args` does not show, and the
# watchdog excludes itself by pid and by script name.
_PAT_ENV=WD_PATTERN
scan() {
  # $1 = shell pattern/regex for awk, $2 = "regex" to use ~ instead of index()
  WD_PATTERN="$1" ps -eo pid,args | WD_PATTERN="$1" awk -v me="$$" -v mode="$2" '
    BEGIN { pat = ENVIRON["WD_PATTERN"] }
    $1 == me { next }
    $0 ~ /pool_watchdog/ { next }
    $0 ~ /[a]wk -v me=/ { next }
    mode == "regex" ? ($0 ~ pat) : (index($0, pat) > 0) { c++ }
    END { print c+0 }'
}
pool_running() { scan "$POOL_MARKER" literal; }
shard_running() { scan "$SHARD_MARKER" regex; }
chain_running() { scan 'run_downstream\.sh' regex; }

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
