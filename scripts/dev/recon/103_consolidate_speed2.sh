RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/consolidate_speed.log
cat > "$RUN/rehearsal/consolidate_speed.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
export PYTHONPATH=$REPO
cd $REPO || exit 1
echo "start $(date -Is)"
rm -f "$RUN/rehearsal/consolidated_check.parquet"*
/usr/bin/time -f "CONSOLIDATE wall=%es maxrss=%MkB" \
  $PY -X utf8 -u scripts/consolidate_factor_values.py \
    --parts "$RUN/delivery/values/parts" \
    --output "$RUN/rehearsal/consolidated_check.parquet"
echo "exit=$?"
echo "--- 校验：行数 / 序列数 / 无重复键 ---"
$PY -X utf8 -u - <<'PYEOF'
import json
from pathlib import Path
import pyarrow.parquet as pq
p = Path("/home/data/agentmatrix_run/rehearsal/consolidated_check.parquet")
side = json.loads(Path(str(p) + ".json").read_text())
print("  sidecar row_count :", format(side["row_count"], ","))
print("  base factors      :", len(side["factors"]))
per = sorted({v["rows"] for v in side["factors"].values()})
print("  rows per series   :", [format(x, ",") for x in per],
      "(all equal)" if len(per) == 1 else "** NOT UNIFORM **")
print("  range             :", side["data_start"], "..", side["data_end"])
df = pq.read_table(p, columns=["date", "code", "factor_name"]).to_pandas()
print("  duplicate keys    :", int(df.duplicated(["date", "code", "factor_name"]).sum()), "(must be 0)")
print("  size              : %.1f MB" % (p.stat().st_size / 1e6))
PYEOF
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/consolidate_speed.sh"
chmod +x "$RUN/rehearsal/consolidate_speed.sh"
setsid nohup bash "$RUN/rehearsal/consolidate_speed.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）"
date -Is
