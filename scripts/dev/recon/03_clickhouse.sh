CH="clickhouse-client"
command -v $CH >/dev/null 2>&1 || CH="/usr/bin/clickhouse-client"
echo "client: $(command -v clickhouse-client || echo 'NOT FOUND')"

echo
echo "===== 数据库列表 ====="
$CH --query "SHOW DATABASES" 2>&1 | head -30

echo
echo "===== 各库磁盘占用 ====="
$CH --query "
SELECT database,
       formatReadableSize(sum(bytes_on_disk)) AS size,
       sum(rows) AS rows,
       count() AS parts
FROM system.parts
WHERE active
GROUP BY database
ORDER BY sum(bytes_on_disk) DESC
" 2>&1 | head -30

echo
echo "===== 所有表 (库.表 / 行数 / 大小) ====="
$CH --query "
SELECT database, table,
       formatReadableSize(sum(bytes_on_disk)) AS size,
       sum(rows) AS rows
FROM system.parts
WHERE active
GROUP BY database, table
ORDER BY sum(bytes_on_disk) DESC
LIMIT 60
" 2>&1 | head -70
