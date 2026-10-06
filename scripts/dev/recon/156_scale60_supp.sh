RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/scale60_supp.log
cat > "$RUN/rehearsal/scale60_supp.sh" <<'EOF'
#!/usr/bin/env bash
# Step 3 alone, with the chain's own arguments (my first attempt invented flag names).
set -u
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
W=$RUN/rehearsal/scale60
RUNS=$RUN/runtime_mirror/data/factor_lab/validation_runs
cd $REPO || exit 1
export PYTHONPATH=$REPO
echo "start $(date -Is)  factors=$(ls -d $RUNS/*/ | wc -l) run dirs"

echo
echo "########## 3. 稳健性附加层（与链中完全相同的参数）##########"
/usr/bin/time -f "  SUPPLEMENT wall=%es maxrss=%MkB" \
  $PY -X utf8 -u scripts/run_robustness_supplement.py \
    --runs-dir "$RUNS" \
    --panel-file "$RUN/panel/validation_panel.parquet" \
    --factor-file "$W/factor_values.parquet" \
    --q 0.05 \
    --jobs 6 \
    --out "$W/supplementary_report.json"
echo "  exit=$?"

echo
echo "  --- 报告摘要 ---"
$PY -X utf8 -u - "$W/supplementary_report.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
print("  顶层键:", sorted(d.keys()))
s = d.get("summary") or {}
print("  summary:", json.dumps(s, ensure_ascii=False))
m = d.get("marginal_effect") or {}
if m:
    print("  marginal:", json.dumps(m, ensure_ascii=False)[:240])
per = d.get("factors") or {}
if isinstance(per, dict) and per:
    have = sum(1 for v in per.values()
               if isinstance(v, dict) and v.get("industry_neutral_retention") not in (None, ""))
    print("  行业中性留存覆盖: %d / %d" % (have, len(per)))
    sample = next(iter(per.items()))
    print("  样例:", json.dumps(sample, ensure_ascii=False)[:220])
PYEOF
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/scale60_supp.sh"
chmod +x "$RUN/rehearsal/scale60_supp.sh"
setsid nohup bash "$RUN/rehearsal/scale60_supp.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached，约 15 分钟）"
date -Is
