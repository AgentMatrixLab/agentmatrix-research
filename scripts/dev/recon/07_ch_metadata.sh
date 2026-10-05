echo "===== users.xml 实际内容 ====="
ls -la /etc/clickhouse-server/users.xml
wc -l /etc/clickhouse-server/users.xml
head -30 /etc/clickhouse-server/users.xml

echo
echo "===== ClickHouse metadata 目录（数据库/表定义） ====="
ls -la /var/lib/clickhouse/metadata/ 2>/dev/null
echo
echo "--- .sql 定义文件 ---"
find /var/lib/clickhouse/metadata -name "*.sql" 2>/dev/null | head -60

echo
echo "===== 库目录 ====="
find /var/lib/clickhouse/metadata -maxdepth 1 -type d 2>/dev/null
