/home/data/conda-envs/rqsdk/bin/python -X utf8 - <<'PYEOF'
import glob, json, collections

paths = sorted(glob.glob("/home/data/agentmatrix_run/shards/shard*/oos/batch_manifest.json"))
print("shard manifests:", len(paths))
FIELDS = ("code_commit","segment","panel_file_sha256","factor_file_sha256",
          "configuration_sha256","data_snapshot_hash","factor_sidecar_data_start",
          "factor_sidecar_data_end","panel_price_basis")
for p in paths:
    pl = json.load(open(p))
    tag = p.split("/")[-3]
    print("---", tag, "keys:", sorted(pl.keys()))
    for f in FIELDS:
        v = pl.get(f)
        if isinstance(v, str) and len(v) > 24:
            v = v[:16] + "..."
        print("    %-26s %r" % (f, v))
    print("    factor_file:", pl.get("factor_file"))
    print("    outputs:", pl.get("outputs"))
    break

print()
print("=== identity 字段在各分片间的差异 ===")
values = collections.defaultdict(set)
for p in paths:
    pl = json.load(open(p))
    for f in FIELDS:
        v = pl.get(f)
        values[f].add(v if not isinstance(v, str) or len(v) <= 40 else v[:20] + "...")
for f in FIELDS:
    vs = values[f]
    flag = "  一致" if len(vs) == 1 else "  **不一致 (%d 种)**" % len(vs)
    print("  %-26s %s" % (f, flag))
    if len(vs) > 1:
        for v in sorted(map(str, vs)):
            print("        ", v)
PYEOF
