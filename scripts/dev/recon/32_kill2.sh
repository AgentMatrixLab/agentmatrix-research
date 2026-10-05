#!/usr/bin/env bash
# The bracket in [r]un_sharded stops the pattern from matching this script's own
# command line -- a plain pkill -f killed the calling shell instead.
for pid in $(ps -eo pid,args | grep -E "[r]un_sharded.sh|[b]uild_factor_values.py|[v]alidate-batch" | awk '{print $1}'); do
  echo "killing $pid"
  kill -TERM "$pid" 2>/dev/null
done
sleep 4
for pid in $(ps -eo pid,args | grep -E "[r]un_sharded.sh|[b]uild_factor_values.py|[v]alidate-batch" | awk '{print $1}'); do
  echo "force killing $pid"
  kill -KILL "$pid" 2>/dev/null
done
sleep 3
echo "--- 残留 ---"
ps -eo pid,args | grep -E "[b]uild_factor|[r]un_sharded|[v]alidate-batch" | cut -c1-90
echo "--- 内存 ---"
free -g | head -2
