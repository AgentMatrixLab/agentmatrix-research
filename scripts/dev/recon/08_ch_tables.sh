echo "===== config.xml 中的 user 配置路径 ====="
grep -n -E "users_config|access_control|path>" /etc/clickhouse-server/config.xml 2>/dev/null | head -10

echo
for db in rqdata amazingdata rqdata_server_validation; do
  echo "########## $db ##########"
  echo "--- 库定义 ---"
  cat /var/lib/clickhouse/metadata/$db.sql 2>/dev/null
  echo "--- 表定义文件 ---"
  find -L /var/lib/clickhouse/metadata/$db -name "*.sql" 2>/dev/null | sort | head -60
  echo "--- 表名 ---"
  find -L /var/lib/clickhouse/metadata/$db -name "*.sql" -printf "%f\n" 2>/dev/null | sed 's/\.sql$//' | sort | head -60
  echo
done
