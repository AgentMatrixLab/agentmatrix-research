echo "===== users.xml 全文（关键段） ====="
grep -v "^\s*<!--" /etc/clickhouse-server/users.xml 2>/dev/null | grep -v "^\s*$" | head -60

echo
echo "===== clickhouse-client 用户级配置 ====="
ls -la /root/.clickhouse-client/ 2>/dev/null
cat /root/.clickhouse-client/config.xml 2>/dev/null
ls -la ~/.clickhouse-client/ 2>/dev/null

echo
echo "===== 找 9000 端口连接串 ====="
grep -rIn --include=*.py --include=*.sh --include=*.ipynb --include=*.md --include=*.txt \
     -E "9000|8123|clickhouse" /home/data/daily_etl.py /home/data/*.py /home/data/RQdata_jobs 2>/dev/null | head -20

echo
echo "===== 全盘搜 clickhouse 连接（限 .py，排除库文件） ====="
grep -rIn --include=*.py -E "clickhouse_connect|clickhouse_driver|8123|Client\(host" \
     /home /root /opt 2>/dev/null | grep -v site-packages | grep -v node_modules | head -20

echo
echo "===== ClickHouse 最近查询日志（看谁在用） ====="
tail -40 /var/log/clickhouse-server/clickhouse-server.log 2>/dev/null | grep -i -E "query|user|connect" | head -15
