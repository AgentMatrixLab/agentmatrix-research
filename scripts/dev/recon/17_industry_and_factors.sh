CH="clickhouse-client --user smartdata_ro --password "$CH_PASSWORD""

echo "===== 行业快照：具体日期 ====="
$CH --query "SELECT DISTINCT query_date FROM rqdata.stock_industry_snapshot ORDER BY query_date" 2>&1 | head -25

echo
echo "===== 中信行业：一级行业数量 ====="
$CH --query "
SELECT first_industry_name, count() AS n
FROM rqdata.stock_industry_snapshot
WHERE query_date = (SELECT max(query_date) FROM rqdata.stock_industry_snapshot)
GROUP BY first_industry_name ORDER BY n DESC LIMIT 35
" 2>&1 | head -40

echo
echo "===== 指数权重：有哪些指数 ====="
$CH --query "
SELECT index_id, count() AS rows, uniqExact(constituent_id) AS members,
       min(requested_date) AS d0, max(requested_date) AS d1
FROM rqdata.index_weight_daily GROUP BY index_id ORDER BY rows DESC LIMIT 12
" 2>&1 | head -16

echo
echo "===== 导出文件里的 91 个因子名 ====="
python3 - <<'PY'
import pyarrow.parquet as pq
f = pq.ParquetFile("/home/data/delivery_export/factor_values_long_2020_2026.parquet")
names = set()
for i in range(min(3, f.metadata.num_row_groups)):
    t = f.read_row_group(i, columns=["factor_name"])
    names.update(t.column("factor_name").to_pylist())
print(f"  (前3个row group) {len(names)} 个: {sorted(names)[:50]}")
PY
