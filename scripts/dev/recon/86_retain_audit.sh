RUN=/home/data/agentmatrix_run
PY=/home/data/conda-envs/rqsdk/bin/python

echo "=== 每个分片：manifest / raw链接 / part 三者是否齐全 ==="
$PY -X utf8 - <<'PYEOF'
import os, glob, json
run = "/home/data/agentmatrix_run"
rows = []
for d in sorted(glob.glob(run + "/shards/shard*")):
    tag = os.path.basename(d)
    man = os.path.join(d, "oos", "batch_manifest.json")
    raw = os.path.join(run, "delivery/values/raw", tag + ".parquet")
    part = os.path.join(run, "delivery/values/parts", tag + ".parquet")
    fv = os.path.join(d, "factor_values.parquet")
    n_pass = "-"
    if os.path.exists(man):
        try:
            pl = json.load(open(man))
            n_pass = sum(1 for r in pl.get("results", [])
                         if r.get("status") == "validated" and not r.get("failed_gates"))
        except Exception:
            n_pass = "?"
    if os.path.exists(man) or os.path.exists(raw) or os.path.exists(part):
        rows.append((tag, os.path.exists(man), os.path.exists(raw), os.path.exists(part),
                     os.path.exists(fv), n_pass))
for tag, m, r, p, f, n in rows:
    flag = ""
    if m and not p and not r:
        flag = "  <<< 有判决但既无链接也无 part（留存 MISS）"
    elif m and not p:
        flag = "  ... 待留存"
    print("  %-9s manifest=%-5s raw=%-5s part=%-5s 因子文件=%-5s 通过=%-3s%s" % (tag, m, r, p, f, n, flag))
print()
print("  manifest 数:", sum(1 for _, m, _, _, _, _ in rows if m),
      " raw链接:", sum(1 for _, _, r, _, _, _ in rows if r),
      " parts:", sum(1 for _, _, _, p, _, _ in rows if p))
PYEOF

echo
echo "=== retain 日志里与 004/005 有关的行 ==="
grep -E 'shard00[45]' "$RUN/logs/retain_daemon.log" 2>/dev/null | tail -20
echo
echo "=== retain 日志里的失败/警告 ==="
grep -iE 'refus|fail|warning|none of|cannot' "$RUN/logs/retain_daemon.log" 2>/dev/null | tail -15
echo
echo "=== pool 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
ps -eo pid,etime,args | awk '/run_one_shard\.sh [0-9]/ {print "    arg=" $NF, "etime=" $2}'
echo "  镜像结果: $(find $RUN/runtime_mirror/data/factor_lab/validation_runs -name validation_result.json 2>/dev/null | wc -l)"
free -g | head -2
df -h / | awk 'NR==2{print "  磁盘可用: "$4}'
date -Is
