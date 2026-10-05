echo "===== ClickHouse access 目录（SQL 定义的用户） ====="
ls -la /var/lib/clickhouse/access/ 2>/dev/null
echo
for f in /var/lib/clickhouse/access/*.sql; do
  echo "--- $f ---"
  cat "$f" 2>/dev/null
  echo
done

echo "===== 是否有 config.xml ====="
ls -la /etc/clickhouse-server/ 2>/dev/null
