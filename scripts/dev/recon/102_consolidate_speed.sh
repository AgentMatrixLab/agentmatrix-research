RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/consolidate_speed.log
cat > "$RUN/rehearsal/consolidate_speed.sh" <<'EOF'
#!/usr/bin/env bash
REPO=/home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
export PYTHONPATH=$REPO
cd $REPO || exit 1
echo "start $(date -Is)"
rm -f "$RUN/rehearsal/consolidated_check.parquet"*
/usr/bin/time -f "CONSOLIDATE wall=%es maxrss=%MkB" \
  $PY -X utf8 -u scripts/consolidate_factor_values.py \
    --parts "$RUN/rehearsal/../delivery/values/parts" \
    --output "$RUN/rehearsal/consolidated_check.parquet"
echo "exit=$?"
echo "--- 校验：行数 / 序列数 / 无重复键 ---"
$PY -X utf8 -u - <<'PYEOF'
import json, pyarrow.parquet as pq
from pathlib import Path
p = Path("/home/data/agentmatrix_run/rehearsal/consolidated_check.parquet")
side = json.loads(Path(str(p) + ".json").read_text())
print("  sidecar row_count :", format(side["row_count"], ","))
print("  base factors      :", len(side["factors"]))
per = sorted({v["rows"] for v in side["factors"].values()})
print("  rows per series   :", [format(x, ",") for x in per], "(all equal)" if len(per) == 1 else "** NOT UNIFORM **")
print("  range             :", side["data_start"], "..", side["data_end"])
# Duplicate-key check on a sample: the freeze rejects duplicate (date, code, factor_name).
import pandas as pd
t = pq.read_table(p, columns=["date", "code", "factor_name"])
df = t.to_pandas()
dups = int(df.duplicated(["date", "code", "factor_name"]).sum())
print("  duplicate keys    :", dups, "(must be 0)")
PYEOF
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/consolidate_speed.sh"
chmod +x "$RUN/rehearsal/consolidate_speed.sh"
setsid nohup bash "$RUN/rehearsal/consolidate_speed.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）"
date -Is
