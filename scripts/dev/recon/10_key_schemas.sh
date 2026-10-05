echo "===== 关键表结构 ====="
for t in stock_price_1d_raw stock_adjust_factor stock_industry_snapshot stock_factor_catalog stock_factor_daily_long ref_index_cn index_weight_daily stock_financial_pit_long ref_calendar_cn; do
  echo "---------- rqdata.$t ----------"
  cat /var/lib/clickhouse/metadata/rqdata/$t.sql 2>/dev/null | head -25
  echo
done
