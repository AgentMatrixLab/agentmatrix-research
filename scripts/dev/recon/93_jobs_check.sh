RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
OUT=$RUN/rehearsal/jobs_check.log
cat > "$RUN/rehearsal/jobs_check.sh" <<'EOF'
#!/usr/bin/env bash
REPO=/home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
RUNS=/home/data/agentmatrix_run/runtime_mirror/data/factor_lab/validation_runs
export PYTHONPATH=$REPO
cd $REPO || exit 1
echo "start $(date -Is)  nproc=$(nproc)"
/usr/bin/time -f "JOBSCHECK wall=%es maxrss=%MkB" \
  $PY -X utf8 -u - <<'PYEOF'
import glob, json, sys, time
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix/scripts")
from run_robustness_supplement import compute_neutral_ic

PANEL = "/home/data/agentmatrix_run/panel/validation_panel.parquet"
parts = sorted(glob.glob("/home/data/agentmatrix_run/delivery/values/parts/*.parquet"))
runs = "/home/data/agentmatrix_run/runtime_mirror/data/factor_lab/validation_runs"

# Use the factors that actually have retained values.
import pyarrow.parquet as pq
have = set()
for p in parts:
    have.update(str(n) for n in pq.read_table(p, columns=["factor_name"]).column(0).to_pylist())

results = []
for path in sorted(glob.glob(runs + "/*/validation_result.json")):
    d = json.load(open(path))
    d.setdefault("factor_id", path.split("/")[-2])
    if d.get("factor_id") in have:
        results.append(d)
print("factors with retained values:", len(results))

t0 = time.time()
serial = compute_neutral_ic(results, __import__("pathlib").Path(PANEL),
                            __import__("pathlib").Path(parts),
                            horizon=10, neutralize_returns=False, jobs=1)
t_serial = time.time() - t0
print("SERIAL   %.1fs  (%d factors, %.2fs each)" % (t_serial, len(serial), t_serial / max(len(serial), 1)))

t0 = time.time()
parallel = compute_neutral_ic(results, __import__("pathlib").Path(PANEL),
                              __import__("pathlib").Path(parts),
                              horizon=10, neutralize_returns=False, jobs=6)
t_par = time.time() - t0
print("PARALLEL %.1fs  speedup %.2fx" % (t_par, t_serial / max(t_par, 1e-9)))

bad = 0
for fid in serial:
    a, b = serial[fid], parallel[fid]
    if (a is None) != (b is None):
        bad += 1; print("  MISMATCH none-ness", fid); continue
    if a is None:
        continue
    for key in ("retention",):
        if abs(a[key] - b[key]) > 1e-12:
            bad += 1; print("  MISMATCH %s %s: %r vs %r" % (fid, key, a[key], b[key]))
    for section in ("raw", "neutral"):
        if abs(a[section]["mean"] - b[section]["mean"]) > 1e-12:
            bad += 1; print("  MISMATCH %s %s.mean" % (fid, section))
print("MISMATCHES:", bad)
PYEOF
echo "exit=$? $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/jobs_check.sh"
chmod +x "$RUN/rehearsal/jobs_check.sh"
setsid nohup bash "$RUN/rehearsal/jobs_check.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）: $OUT"
date -Is
