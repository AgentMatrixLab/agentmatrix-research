#!/usr/bin/env bash
# Measure how much RSS loading one real factor file costs, after the categorical fix.
cd /home/data/agentmatrix_run/agentmatrix || exit 1
export PYTHONPATH=/home/data/agentmatrix_run/agentmatrix

cat > /tmp/measure_load.py <<'PYEOF'
import sys
from research_core.factor_lab.precomputed_factors import load_precomputed_factors

path = sys.argv[1]
pre = load_precomputed_factors(path)
print("series:", len(pre.series))
print("rows:", sum(len(s) for s in pre.series.values()))
print("dtypes:", set(str(s.index.dtypes[1]) for s in list(pre.series.values())[:3]))
PYEOF

/usr/bin/time -v /home/data/conda-envs/rqsdk/bin/python -X utf8 /tmp/measure_load.py \
    /home/data/agentmatrix_run/memtest/factor_values.parquet 2>&1 \
  | grep -E "series:|rows:|dtypes:|Maximum resident|Elapsed \(wall"
