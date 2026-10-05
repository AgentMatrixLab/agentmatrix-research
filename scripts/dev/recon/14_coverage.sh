CH="clickhouse-client --user smartdata_ro --password <redacted>"

echo "===== stock_price_1d_raw: 日期范围 / 股票数 / adjust_type ====="
$CH --query "
SELECT adjust_type, count() AS rows, uniqExact(order_book_id) AS stocks,
       min(trade_date) AS d0, max(trade_date) AS d1
FROM rqdata.stock_price_1d_raw GROUP BY adjust_type ORDER BY rows DESC
" 2>&1 | head -10

echo
echo "===== 覆盖的交易日数 ====="
$CH --query "
SELECT toYear(trade_date) AS y, countDistinct(trade_date) AS days, count() AS rows,
       uniqExact(order_book_id) AS stocks
FROM rqdata.stock_price_1d_raw WHERE adjust_type='post'
GROUP BY y ORDER BY y
" 2>&1 | head -20

echo
echo "===== 因子目录（10443 条）构成 ====="
$CH --query "
SELECT factor_type, count() AS n, sum(is_alpha101) AS alpha101,
       sum(is_technical) AS technical, sum(is_financial_derived) AS fin_derived,
       sum(calculation_logic IS NOT NULL AND calculation_logic != '') AS with_logic
FROM rqdata.stock_factor_catalog GROUP BY factor_type ORDER BY n DESC
" 2>&1 | head -20

echo
echo "===== 因子值：日期范围 / 因子数 ====="
$CH --query "
SELECT min(trade_date) AS d0, max(trade_date) AS d1,
       uniqExact(factor_name) AS factors, uniqExact(order_book_id) AS stocks,
       count() AS rows
FROM rqdata.stock_factor_daily_long
" 2>&1 | head -5

echo
echo "===== 行业分类快照 ====="
$CH --query "
SELECT industry_source, count() AS n, uniqExact(order_book_id) AS stocks,
       min(query_date) AS d0, max(query_date) AS d1, countDistinct(query_date) AS snapshots
FROM rqdata.stock_industry_snapshot GROUP BY industry_source ORDER BY n DESC
" 2>&1 | head -15

echo
echo "===== 指数成分 / 权重 ====="
$CH --query "
SELECT index_code, count() AS rows, min(trade_date) AS d0, max(trade_date) AS d1
FROM (
  SELECT toString(order_book_id) AS index_code, trade_date FROM rqdata.index_weight_daily
) GROUP BY index_code ORDER BY rows DESC LIMIT 10
" 2>&1 | head -15
