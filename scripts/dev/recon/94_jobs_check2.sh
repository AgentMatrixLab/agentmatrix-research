RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/jobs_check.log
cat > "$RUN/rehearsal/jobs_check2.sh" <<'EOF'
#!/usr/bin/env bash
REPO=/home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
export PYTHONPATH=$REPO
cd $REPO || exit 1
echo "start $(date -Is)  nproc=$(nproc)"
/usr/bin/time -f "JOBSCHECK wall=%es maxrss=%MkB" \
  $PY -X utf8 -u - <<'PYEOF'
import glob, json, sys, time
from pathlib import Path
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix/scripts")
from run_robustness_supplement import compute_neutral_ic
import pyarrow.parquet as pq

PANEL = Path("/home/data/agentmatrix_run/panel/validation_panel.parquet")
PARTS = Path("/home/data/agentmatrix_run/delivery/values/parts")   # a DIRECTORY
RUNS = "/home/data/agentmatrix_run/runtime_mirror/data/factor_lab/validation_runs"

have = set()
for p in sorted(glob.glob(str(PARTS / "*.parquet"))):
    have.update(str(n) for n in pq.read_table(p, columns=["factor_name"]).column(0).to_pylist())

results = []
for path in sorted(glob.glob(RUNS + "/*/validation_result.json")):
    d = json.load(open(path))
    d.setdefault("factor_id", path.split("/")[-2])
    if d.get("factor_id") in have:
        results.append(d)
print("factors with retained values:", len(results), flush=True)

t0 = time.time()
serial = compute_neutral_ic(results, PANEL, PARTS, horizon=10,
                            neutralize_returns=False, jobs=1)
t_serial = time.time() - t0
print("SERIAL   %.1fs  (%d factors, %.2fs each)" % (
    t_serial, len(serial), t_serial / max(len(serial), 1)), flush=True)

t0 = time.time()
parallel = compute_neutral_ic(results, PANEL, PARTS, horizon=10,
                              neutralize_returns=False, jobs=6)
t_par = time.time() - t0
print("PARALLEL %.1fs  speedup %.2fx  (%.2fs each)" % (
    t_par, t_serial / max(t_par, 1e-9), t_par / max(len(parallel), 1)), flush=True)

bad = 0
for fid in serial:
    a, b = serial[fid], parallel[fid]
    if (a is None) != (b is None):
        bad += 1; print("  MISMATCH none-ness", fid); continue
    if a is None:
        continue
    if abs(a["retention"] - b["retention"]) > 1e-12:
        bad += 1; print("  MISMATCH retention", fid)
    for section in ("raw", "neutral"):
        if abs(a[section]["mean"] - b[section]["mean"]) > 1e-12:
            bad += 1; print("  MISMATCH %s.%s" % (fid, section))
print("MISMATCHES:", bad)
PYEOF
echo "exit=$? $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/jobs_check2.sh"
chmod +x "$RUN/rehearsal/jobs_check2.sh"
setsid nohup bash "$RUN/rehearsal/jobs_check2.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）"
sleep 15
head -5 "$OUT"
date -Is
