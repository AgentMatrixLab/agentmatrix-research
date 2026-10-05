RUN=/home/data/agentmatrix_run
PY=/home/data/conda-envs/rqsdk/bin/python
echo "=== shard023 / shard024 的候选公式 ==="
$PY -X utf8 - <<'PYEOF'
import csv
for tag in ("shard023", "shard024", "shard022"):
    path = "/home/data/agentmatrix_run/shards/%s/candidate_list.csv" % tag
    try:
        rows = list(csv.DictReader(open(path, encoding="utf-8")))
    except Exception as exc:
        print("  %s: %s" % (tag, exc)); continue
    print("--- %s" % tag)
    for r in rows:
        f = (r.get("formula") or "")
        print("    %-26s w=%-4s len=%-4d %s" % (r.get("factor_id"), r.get("window"), len(f), f[:80]))
PYEOF

echo
echo "=== 全量候选里公式长度分布（长度≈复杂度，可用作慢因子的代理）==="
$PY -X utf8 - <<'PYEOF'
import csv, statistics
rows = list(csv.DictReader(open("/home/data/agentmatrix_run/candidate_list.csv", encoding="utf-8")))
lens = [(len(r.get("formula") or ""), r["factor_id"], r.get("window")) for r in rows]
lens.sort(reverse=True)
print("  候选总数: %d" % len(lens))
print("  公式长度: 中位 %d, 均值 %.0f, 最大 %d" % (
    statistics.median([x[0] for x in lens]), statistics.mean([x[0] for x in lens]), lens[0][0]))
print("  最长 8 个:")
for L, fid, w in lens[:8]:
    print("    len=%-4d w=%-4s %s" % (L, w, fid))
# Which shards hold the longest formulas (round-robin: index % 213)
import collections
shard_len = collections.defaultdict(list)
for index, (_L, fid, _w) in enumerate([(len(r.get("formula") or ""), r["factor_id"], r.get("window")) for r in rows]):
    shard_len[index % 213].append(_L)
worst = sorted(shard_len.items(), key=lambda kv: -sum(kv[1]))[:8]
print("  公式总长最大的 8 个分片（推测最慢）:")
for shard, vals in worst:
    print("    shard%03d  total_len=%-5d per_candidate=%s" % (shard, sum(vals), vals))
PYEOF
date -Is
