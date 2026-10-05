cd /home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
export PYTHONPATH=/home/data/agentmatrix_run/agentmatrix

echo "===== 1. 面板契约校验 ====="
$PY -X utf8 - <<'EOF'
import sys
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
from research_core.factor_lab.panel_source import load_validation_panel

panel = load_validation_panel("/home/data/agentmatrix_run/panel/validation_panel.parquet")
print(f"  rows         : {len(panel.frame):,}")
print(f"  price_basis  : {panel.price_basis}")
print(f"  extended     : {panel.extended_columns}")
print(f"  missing ext  : {panel.missing_extended_columns()}")
print(f"  date range   : {panel.frame['date'].min().date()} .. {panel.frame['date'].max().date()}")
print(f"  codes        : {panel.frame['code'].nunique():,}")
EOF

echo
echo "===== 2. 生成 849 候选清单 ====="
$PY -X utf8 scripts/build_candidate_list.py --out /home/data/agentmatrix_run/candidate_list.csv 2>&1 | head -18

echo
echo "===== 3. 候选清单契约校验 ====="
$PY -X utf8 scripts/dev/validate_candidate_list.py /home/data/agentmatrix_run/candidate_list.csv 2>&1 | head -14

echo
echo "===== 4. 磁盘 ====="
df -h / | tail -1
