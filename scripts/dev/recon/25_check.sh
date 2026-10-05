echo "--- build log ---"
tail -20 /home/data/agentmatrix_run/logs/pilot_build.log 2>/dev/null
echo
echo "--- process ---"
ps -eo pid,rss,etime,args | grep build_factor | grep -v grep | cut -c1-120
echo
echo "--- pilot dir ---"
ls -la /home/data/agentmatrix_run/pilot/ 2>&1 | head
echo
echo "--- free ---"
free -g | head -2
