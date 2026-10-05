cd /home/data/delivery_export
python3 - <<'PY'
import pyarrow.parquet as pq, json, os
for name in ("rqdata_panel.parquet", "benchmark_000985.parquet", "reversal_1m_2020_2026.parquet"):
    if not os.path.exists(name):
        print(f"--- {name}: MISSING ---"); continue
    f = pq.ParquetFile(name)
    print(f"--- {name} ---")
    print(f"  rows={f.metadata.num_rows:,}  row_groups={f.metadata.num_row_groups}")
    print(f"  columns={f.schema_arrow.names}")
    print()
PY

echo "===== 大文件只读元数据 ====="
python3 - <<'PY'
import pyarrow.parquet as pq
f = pq.ParquetFile("/home/data/delivery_export/factor_values_long_2020_2026.parquet")
print("factor_values_long_2020_2026.parquet")
print(f"  rows={f.metadata.num_rows:,}  row_groups={f.metadata.num_row_groups}")
print(f"  columns={f.schema_arrow.names}")
PY
