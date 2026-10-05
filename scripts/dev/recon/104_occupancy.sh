RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/occupancy.log
cat > "$RUN/rehearsal/occupancy.sh" <<'EOF'
#!/usr/bin/env bash
# Where does the throughput go?
#
# With the oos phase serialised, the arithmetic ceiling is one shard per oos duration:
# 562 s -> 6.4 shards/hour for a perfectly fed pipeline. Measured throughput is ~5.0, so
# roughly a fifth of the time the oos slot is idle. This samples the phase of every worker
# to find out whether that is real, and where.
MARK=mark_occ
oos_busy=0; oos_idle=0; total=0
both_light=0; idle_slot_with_work=0
i=0
echo "start $(date -Is)"
printf "%6s %5s %5s %5s %8s %6s\n" "t" "build" "train" "oos" "availGB" "slot"
while [ $i -lt 100 ]; do
  b=$(ps -eo args | awk -v m="$MARK" '$0 !~ m && /build_factor_values/ {c++} END {print c+0}')
  t=$(ps -eo args | awk -v m="$MARK" '$0 !~ m && /validate-batch/ && /--segment train/ {c++} END {print c+0}')
  o=$(ps -eo args | awk -v m="$MARK" '$0 !~ m && /validate-batch/ && /--segment oos/ {c++} END {print c+0}')
  # Each worker shows up twice in ps (/usr/bin/time wrapper + python child).
  b=$((b / 2)); t=$((t / 2)); o=$((o / 2))
  [ "$o" -ge 2 ] && o=2
  a=$(free -g | awk '/^Mem:/{print $7}')
  slot="idle"; [ "$o" -gt 0 ] && slot="BUSY"
  total=$((total + 1))
  if [ "$o" -gt 0 ]; then oos_busy=$((oos_busy + 1)); else oos_idle=$((oos_idle + 1)); fi
  # Both workers in a light phase (build) with the oos slot idle = the bubble.
  [ "$o" -eq 0 ] && [ "$b" -ge 1 ] && idle_slot_with_work=$((idle_slot_with_work + 1))
  printf "%6s %5s %5s %5s %8s %6s\n" "$i" "$b" "$t" "$o" "$a" "$slot"
  i=$((i + 1))
  sleep 15
done
echo
echo "samples              : $total"
echo "oos slot BUSY        : $oos_busy  ($(( 100 * oos_busy / total ))%)"
echo "oos slot idle        : $oos_idle  ($(( 100 * oos_idle / total ))%)"
echo "idle while building  : $idle_slot_with_work"
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/occupancy.sh"
chmod +x "$RUN/rehearsal/occupancy.sh"
setsid nohup bash "$RUN/rehearsal/occupancy.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动占用率采样（约 25 分钟）"
date -Is
