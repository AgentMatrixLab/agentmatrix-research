echo "===== conda 环境 ====="
ls /opt/conda/envs 2>/dev/null; ls /root/miniconda3/envs 2>/dev/null; ls /home/data/conda-envs 2>/dev/null
echo "--- which conda ---"
which conda 2>/dev/null; ls -d /opt/conda /root/miniconda3 /usr/local/conda 2>/dev/null

echo
echo "===== rqsdk 环境的 python 与关键包 ====="
PY=/home/data/conda-envs/rqsdk/bin/python
ls -la $PY 2>/dev/null && $PY -V
$PY -c "
import importlib
for m in ['pandas','numpy','pyarrow','scipy','yaml','statsmodels','rqdatac','pytest']:
    try:
        mod=importlib.import_module(m); print(f'  {m:14}', getattr(mod,'__version__','?'))
    except Exception as e:
        print(f'  {m:14} MISSING')
" 2>&1 | head -12

echo
echo "===== 容量测算 ====="
echo "面板 2020-2026 的 (date,code) 对数："
clickhouse-client --user smartdata_ro --password "$CH_PASSWORD" --query "
SELECT count() FROM rqdata.stock_price_1d_raw
WHERE adjust_type='none' AND trade_date >= '2020-01-02' AND trade_date <= '2026-08-31'
" 2>&1 | head -3

echo
echo "===== 工作目录 ====="
mkdir -p /home/data/agentmatrix_run && echo "created /home/data/agentmatrix_run"
df -h /home/data | tail -1
