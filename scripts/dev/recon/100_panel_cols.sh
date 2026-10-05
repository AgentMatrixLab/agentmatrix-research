RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/panel_cols.log
cat > "$RUN/rehearsal/panel_cols.sh" <<'EOF'
#!/usr/bin/env bash
REPO=/home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
export PYTHONPATH=$REPO
cd $REPO || exit 1
echo "start $(date -Is)"
/usr/bin/time -f "PANELCOLS wall=%es maxrss=%MkB" $PY -X utf8 -u - <<'PYEOF'
import resource, sys, time
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
from research_core.factor_lab.streaming_supplement import prepare_panel

PANEL = "/home/data/agentmatrix_run/panel/validation_panel.parquet"

def rss_gb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576

# 1. Equivalence: the schema must describe exactly what a full read would report.
t0 = time.time()
full_cols = pd.read_parquet(PANEL).columns.tolist()
t_full_cols = time.time() - t0
t0 = time.time()
schema_cols = list(pq.ParquetFile(PANEL).schema_arrow.names)
t_schema = time.time() - t0
print("full read for .columns : %.1fs  (%d cols)" % (t_full_cols, len(full_cols)))
print("schema-only            : %.2fs  (%d cols)" % (t_schema, len(schema_cols)))
print("IDENTICAL COLUMN LISTS :", full_cols == schema_cols)
assert full_cols == schema_cols, "schema and data disagree about the columns"

# 2. prepare_panel now reads four columns.
before = rss_gb()
t0 = time.time()
panel = prepare_panel(PANEL, horizon=10)
t_new = time.time() - t0
after = rss_gb()
print()
print("prepare_panel columns  : %s" % list(panel.columns))
print("prepare_panel time     : %.1fs" % t_new)
print("process peak RSS       : %.1f GB" % after)
print("rows x cols            : %s x %d" % (format(len(panel), ","), panel.shape[1]))
PYEOF
echo "exit=$? $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/panel_cols.sh"
chmod +x "$RUN/rehearsal/panel_cols.sh"
setsid nohup bash "$RUN/rehearsal/panel_cols.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）"
date -Is
