CH="/usr/local/bin/clickhouse-client"
PW="<redacted>"
echo "===== stock_shares 结构 ====="
"$CH" --user smartdata_ro --password "$PW" --query "DESCRIBE TABLE rqdata.stock_shares" 2>&1 | head -20
echo "--- 样例 ---"
"$CH" --user smartdata_ro --password "$PW" --query "SELECT * FROM rqdata.stock_shares LIMIT 2 FORMAT Vertical" 2>&1 | head -25
echo
echo "===== stock_security_state_daily 结构（停牌/ST） ====="
"$CH" --user smartdata_ro --password "$PW" --query "DESCRIBE TABLE rqdata.stock_security_state_daily" 2>&1 | head -20
echo
echo "===== stock_price_1d_raw 的 num_trades 可用性 ====="
"$CH" --user smartdata_ro --password "$PW" --query "SELECT count() AS total, count(num_trades) AS with_trades FROM rqdata.stock_price_1d_raw WHERE adjust_type='none'" 2>&1 | head -3
