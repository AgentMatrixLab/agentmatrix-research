CH="clickhouse-client --user smartdata_ro --password "$CH_PASSWORD""

echo "===== 连通性 ====="
$CH --query "SELECT version()" 2>&1 | head -3

echo
echo "===== 库大小 ====="
$CH --query "
SELECT database,
       formatReadableSize(sum(bytes_on_disk)) AS size,
       sum(rows) AS rows,
       count() AS active_parts
FROM system.parts WHERE active
GROUP BY database ORDER BY sum(bytes_on_disk) DESC
" 2>&1 | head -20

echo
echo "===== rqdata 库各表 ====="
$CH --query "
SELECT table,
       formatReadableSize(sum(bytes_on_disk)) AS size,
       sum(rows) AS rows
FROM system.parts WHERE active AND database='rqdata'
GROUP BY table ORDER BY sum(bytes_on_disk) DESC
" 2>&1 | head -60
