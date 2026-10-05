CH="/usr/local/bin/clickhouse-client"
PW="<redacted>"
echo "===== security_state_daily.industry_code 覆盖 ====="
"$CH" --user smartdata_ro --password "$PW" --query "
SELECT min(trade_date) AS d0, max(trade_date) AS d1, count() AS rows,
       countIf(industry_code IS NOT NULL AND industry_code != '') AS with_industry,
       uniqExact(industry_code) AS distinct_codes
FROM rqdata.stock_security_state_daily
" 2>&1 | head -5

echo
echo "===== 按年看 industry_code 覆盖 ====="
"$CH" --user smartdata_ro --password "$PW" --query "
SELECT toYear(trade_date) AS y, count() AS rows,
       countIf(industry_code IS NOT NULL AND industry_code != '') AS with_industry
FROM rqdata.stock_security_state_daily
GROUP BY y ORDER BY y
" 2>&1 | head -14

echo
echo "===== industry_code 样例 + 是否与中信一致 ====="
"$CH" --user smartdata_ro --password "$PW" --query "
SELECT industry_code, count() AS n FROM rqdata.stock_security_state_daily
WHERE trade_date='2021-06-30' GROUP BY industry_code ORDER BY n DESC LIMIT 10
" 2>&1 | head -14

echo
echo "===== industry_snapshot 里有哪些 industry_source ====="
"$CH" --user smartdata_ro --password "$PW" --query "
SELECT industry_source, count() AS n, min(query_date) AS d0, max(query_date) AS d1,
       uniqExact(first_industry_name) AS n_industries
FROM rqdata.stock_industry_snapshot GROUP BY industry_source
" 2>&1 | head -8
