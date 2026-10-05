echo "=== 1. bash printf 对前导零参数的真实语义（决定性证据）==="
echo "bash: $BASH_VERSION"
for i in 000 001 007 008 009 010 011 012 017 018 019 020 029 077 078 099 100 213; do
  out=$(printf "%03d" "$i" 2>&1)
  printf "  arg=%-4s -> %%03d=%-6s TAG=shard-%s\n" "$i" "$out" "$out"
done

echo
echo "=== 2. 服务器上 run_one_shard.sh 当前内容（TAG 一行）==="
grep -n 'TAG=' /home/data/agentmatrix_run/agentmatrix/scripts/dev/run_one_shard.sh

echo
echo "=== 3. pool 是否还在跑 / 分片是否被清空 ==="
echo "  oos 完成: $(ls /home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)"
echo "  分片目录: $(ls -d /home/data/agentmatrix_run/shards/shard* 2>/dev/null | wc -l)"
echo "  被移开的 run1 分片: $(ls -d /home/data/agentmatrix_run/reference/run1/shard*_run1 2>/dev/null | wc -l)"
ps -eo pid,etime,args | awk '/run_pool|run_one_shard|xargs -P/ {print "  " $1, $2, $3, $4, $5, $6, $7}'

echo
echo "=== 4. todo.txt 前几行与被 dispatch 的参数 ==="
head -5 /home/data/agentmatrix_run/logs/todo.txt 2>/dev/null | sed 's/^/  /'
echo "  todo 行数: $(wc -l < /home/data/agentmatrix_run/logs/todo.txt 2>/dev/null)"

echo
echo "=== 5. pool 日志里是否有 printf 报错 ==="
grep -ci 'octal\|invalid number' /home/data/agentmatrix_run/logs/*.log 2>/dev/null | grep -v ':0' || echo "  无 octal 报错记录"

echo
echo "=== 6. 已完成分片是否自洽（manifest 的 candidate 数与目录里的 candidate_list 是否一致）==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import csv, glob, json, os
bad = 0
for path in sorted(glob.glob("/home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json")):
    d = os.path.dirname(os.path.dirname(path))
    tag = os.path.basename(d)
    pl = json.load(open(path))
    cl = os.path.join(d, "candidate_list.csv")
    n = sum(1 for _ in open(cl, encoding="utf-8")) - 1 if os.path.exists(cl) else None
    ids = sorted(r["factor_id"] for r in pl.get("results", []))
    rows = []
    if os.path.exists(cl):
        rows = sorted(r["factor_id"] for r in csv.DictReader(open(cl, encoding="utf-8")))
    ok = (n == pl.get("candidate_count")) and (ids == rows)
    if not ok:
        bad += 1
    print("  %s  manifest_count=%s  dir_rows=%s  因子集合一致=%s  %s" % (
        tag, pl.get("candidate_count"), n, ids == rows, "OK" if ok else "<<< 不一致"))
print("  不一致分片数:", bad)
PYEOF
date -Is
