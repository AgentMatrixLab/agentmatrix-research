RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/rss_profile.log
cat > "$RUN/rehearsal/rss_profile.sh" <<'EOF'
#!/usr/bin/env bash
# Profile RAM during the oos phase.
#
# The oos lock exists because two workers peaking at 28 GB each need 56 GB on a 62 GB shared
# box. That reasoning assumed the peak is SUSTAINED. If instead RSS sits low and spikes
# briefly, two oos phases could overlap safely with a memory guard, which would roughly double
# throughput -- the difference between delivering on 10-07 and on 10-06.
MARK=mark_rss_prof
echo "start $(date -Is)  nproc=$(nproc)"
printf "%-10s %-8s %-10s %-10s %-8s\n" "elapsed" "phase" "rss_max_GB" "rss_sum_GB" "avail_GB"
i=0
while [ $i -lt 78 ]; do
  rss=$(ps -eo rss,args | awk -v m="$MARK" '$0 !~ m && /validate-batch/ && /--segment oos/ {s+=$1; if ($1>mx) mx=$1} END {printf "%.1f %.1f", mx/1048576, s/1048576}')
  max=$(echo "$rss" | cut -d' ' -f1)
  sum=$(echo "$rss" | cut -d' ' -f2)
  n=$(ps -eo args | awk -v m="$MARK" '$0 !~ m && /validate-batch/ && /--segment oos/ {c++} END {print c+0}')
  t=$(ps -eo args | awk -v m="$MARK" '$0 !~ m && /validate-batch/ && /--segment train/ {c++} END {print c+0}')
  phase="idle"
  [ "$n" -gt 0 ] && phase="oos"
  [ "$t" -gt 0 ] && [ "$n" -gt 0 ] && phase="oos+train"
  [ "$t" -gt 0 ] && [ "$n" -eq 0 ] && phase="train"
  printf "%-10s %-8s %-10s %-10s %-8s\n" "${max:-0}" "${sum:-0}" "$(free -g | awk '/^Mem:/{print $7}')" "$phase" "$(date +%H:%M:%S)"
  i=$((i + 1))
  sleep 10
done
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/rss_profile.sh"
chmod +x "$RUN/rehearsal/rss_profile.sh"
setsid nohup bash "$RUN/rehearsal/rss_profile.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动 RSS profiling（约 13 分钟）"
sleep 5
head -3 "$OUT"
date -Is
