RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/package_check.log
cat > "$RUN/rehearsal/package_check.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
W=$RUN/rehearsal/scale30
cd $REPO || exit 1
export PYTHONPATH=$REPO
echo "start $(date -Is)"
rm -rf "$W/package"
/usr/bin/time -f "PACKAGE wall=%es maxrss=%MkB" \
  $PY -X utf8 -u scripts/package_delivery.py \
    --output-dir "$W/package" \
    --batch-manifest "$W/merged/batch_manifest.json" \
    --candidates "$W/batch_candidates.csv" > "$W/package.stdout" 2>&1
echo "package exit=$?（0 = 有内容；4 = 空包；2 = 输入错误）"
echo
echo "--- stdout 摘要 ---"
$PY -X utf8 -u - "$W/package.stdout" <<'PYEOF'
import json, sys
text = open(sys.argv[1], encoding="utf-8").read()
try:
    d = json.loads(text)
except Exception:
    print(text[:1200]); raise SystemExit(0)
print("  counts          :", json.dumps(d.get("counts"), ensure_ascii=False))
print("  included        :", len(d.get("included_factors", [])))
print("  excluded        :", len(d.get("excluded_factors", [])))
print("  factor_catalog  :", d.get("factor_catalog_csv"))
if d.get("warning"):
    print("  warning         :", d["warning"])
PYEOF
echo
echo "--- 包内容 ---"
ls -la "$W/package" 2>/dev/null | head -12
echo "  文件总数: $(find "$W/package" -type f 2>/dev/null | wc -l)"
echo "  目录数  : $(find "$W/package" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)"
echo
echo "--- package_manifest.json 摘要 ---"
$PY -X utf8 -u - "$W/package/package_manifest.json" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as exc:
    print("  读取失败:", exc); raise SystemExit(0)
print("  顶层键:", sorted(d.keys()))
print("  generated_at:", d.get("generated_at"))
print("  counts:", json.dumps(d.get("counts"), ensure_ascii=False))
inc = d.get("included_factors") or []
if inc:
    print("  首个 included 条目:", json.dumps(inc[0], ensure_ascii=False)[:300])
exc = d.get("excluded_factors") or []
if exc:
    print("  首个 excluded 条目:", json.dumps(exc[0], ensure_ascii=False)[:220])
PYEOF
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/package_check.sh"
chmod +x "$RUN/rehearsal/package_check.sh"
setsid nohup bash "$RUN/rehearsal/package_check.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）"
date -Is
