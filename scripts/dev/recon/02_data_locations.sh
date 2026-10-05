echo "===== /var 细分 ====="
du -sh /var/* 2>/dev/null | sort -rh | head -10
echo
echo "===== ClickHouse 数据目录 ====="
du -sh /var/lib/clickhouse/* 2>/dev/null | sort -rh | head -15
echo
echo "===== ClickHouse 服务 ====="
systemctl is-active clickhouse-server 2>/dev/null || echo "(no systemd unit)"
ps aux | grep -i clickhouse | grep -v grep | head -5
echo
echo "===== /home/data 顶层 ====="
ls -la /home/data/ 2>/dev/null | head -45
echo
echo "===== /home/data 各子目录大小 ====="
du -sh /home/data/*/ 2>/dev/null | sort -rh | head -25
