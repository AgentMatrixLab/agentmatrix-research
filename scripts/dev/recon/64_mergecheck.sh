RUN=/home/data/agentmatrix_run
echo "=== A. identity 字段跨分片一致性（决定 step1 能否合并）==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, json, collections
paths = sorted(glob.glob("/home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json"))
FIELDS = ("code_commit","segment","panel_file_sha256","factor_file_sha256",
          "configuration_sha256","data_snapshot_hash","factor_sidecar_data_start",
          "factor_sidecar_data_end","panel_price_basis")
print("shard manifests:", len(paths))
pl0 = json.load(open(paths[0]))
print("manifest keys:", sorted(pl0.keys()))
print()
values = collections.defaultdict(set)
for p in paths:
    pl = json.load(open(p))
    for f in FIELDS:
        v = pl.get(f)
        values[f].add(v if not isinstance(v, str) or len(v) <= 24 else v[:20] + "...")
for f in FIELDS:
    vs = values[f]
    print("  %-26s %s" % (f, "一致" if len(vs) == 1 else "**不一致 (%d 种)**" % len(vs)))
    if len(vs) > 1:
        for v in sorted(map(str, vs)):
            print("        ", v)
print()
print("factor_file 字段（各分片应不同）:")
for p in paths[:4]:
    pl = json.load(open(p))
    print("   ", p.split("/")[-3], "->", pl.get("factor_file"))
PYEOF

echo
echo "=== B. 单分片各阶段耗时 / 峰值内存（来自 /usr/bin/time）==="
for f in $RUN/logs/shard0*.log; do
  echo "--- $(basename $f)"
  grep -E 'maxrss|start |done ' "$f" | sed 's/^/    /'
done

echo
echo "=== C. 分片产物大小（在跑的 010/011 因子文件还在）==="
ls -la $RUN/shards/shard010/ $RUN/shards/shard011/ 2>/dev/null | grep -E 'parquet|json|csv|total'
echo
du -sh $RUN/shards 2>/dev/null
