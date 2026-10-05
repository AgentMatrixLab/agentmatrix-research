RUN=/home/data/agentmatrix_run
cat > /tmp/passrate.py <<'PYEOF'
import glob, json, collections

rows = []
for path in sorted(glob.glob("/home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json")):
    payload = json.load(open(path))
    for entry in payload.get("results", []):
        rows.append(entry)

print(f"已完成分片里的因子结果数: {len(rows)}")
if not rows:
    raise SystemExit(0)

status = collections.Counter(r.get("status") for r in rows)
print("状态:", dict(status))

passed = [r for r in rows if r.get("status") == "validated" and not r.get("failed_gates")]
print(f"通过全部冻结门槛: {len(passed)}/{len(rows)} = {len(passed)/len(rows):.1%}")

gates = collections.Counter()
for r in rows:
    for g in (r.get("failed_gates") or []):
        gates[g] += 1
print("\n各门槛失败次数（分母 %d）:" % len(rows))
for gate, n in gates.most_common():
    print(f"  {gate:<28} {n:>3}  ({n/len(rows):.0%})")

print("\n按家族:")
fam = collections.defaultdict(lambda: [0, 0])
for r in rows:
    f = r["factor_id"].split(":")[0]
    fam[f][0] += 1
    if r.get("status") == "validated" and not r.get("failed_gates"):
        fam[f][1] += 1
for f in sorted(fam):
    total, ok = fam[f]
    print(f"  {f:<10} {ok}/{total}")

print("\n通过的因子:")
for r in passed:
    print("  ", r["factor_id"])
PYEOF

/home/data/conda-envs/rqsdk/bin/python -X utf8 /tmp/passrate.py
echo
echo "=== 进度 ==="
echo "  oos 完成: $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l) / 213"
echo "  驱动启动: $(grep -c started $RUN/logs/sharded_driver.log)"
date -Is
