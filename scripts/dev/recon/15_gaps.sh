CH="clickhouse-client --user smartdata_ro --password "$CH_PASSWORD""

echo "===== 已存在的导出：侧车全文 ====="
for f in rqdata_panel.parquet.json benchmark_000985.parquet.json factor_values_long_2020_2026.parquet.json; do
  echo "---------- $f ----------"
  python3 -c "import json,sys; print(json.dumps(json.load(open('/home/data/delivery_export/$f')), ensure_ascii=False, indent=1))" 2>/dev/null || cat "/home/data/delivery_export/$f"
  echo
done

echo "===== index_weight_daily 结构 ====="
$CH --query "DESCRIBE TABLE rqdata.index_weight_daily" 2>&1 | head -15

echo
echo "===== 指数权重：哪些指数 / 日期范围 ====="
$CH --query "
SELECT index_code, count() AS rows, uniqExact(order_book_id) AS members,
       min(trade_date) AS d0, max(trade_date) AS d1
FROM rqdata.index_weight_daily GROUP BY index_code ORDER BY rows DESC LIMIT 12
" 2>&1 | head -18

echo
echo "===== RQData 自带的 300 个因子是什么 ====="
$CH --query "
SELECT factor_type, uniqExact(factor_name) AS n
FROM rqdata.stock_factor_daily_long GROUP BY factor_type ORDER BY n DESC
" 2>&1 | head -15

echo
echo "===== 这 300 个因子的名字（前 40） ====="
$CH --query "SELECT DISTINCT factor_name FROM rqdata.stock_factor_daily_long ORDER BY factor_name LIMIT 40" 2>&1 | head -45

echo
echo "===== stock_price_1d_raw 调整类型分布（确认只有 none） ====="
$CH --query "
SELECT adjust_type, count() AS rows, min(trade_date) AS d0, max(trade_date) AS d1
FROM rqdata.stock_price_1d_raw GROUP BY adjust_type
" 2>&1 | head -8
