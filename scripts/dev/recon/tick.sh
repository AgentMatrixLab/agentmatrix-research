RUN=/home/data/agentmatrix_run
D=$(ls "$RUN"/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)
P=$(ls "$RUN"/delivery/values/parts/*.parquet 2>/dev/null | wc -l)
/home/data/conda-envs/rqsdk/bin/python -X utf8 - "$RUN" "$D" "$P" <<'PYEOF'
import glob, json, sys
run, done, parts = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
passed = 0
for path in glob.glob(f"{run}/shards/shard*/oos/batch_manifest.json"):
    try:
        payload = json.load(open(path))
    except Exception:
        continue
    passed += sum(1 for r in payload.get("results", [])
                  if r.get("status") == "validated" and not r.get("failed_gates"))
rate = passed / done if done else 0
need = 330 - passed
hours = (need / rate / 6.4) if rate else 0
print(f"shards={done} parts={parts} passed={passed} "
      f"to330={max(need,0)} eta_h={hours:.1f} "
      f"parts_ok={'yes' if parts == done else 'NO'}")
import os
print("triggered=" + ("yes" if os.path.exists(f"{run}/logs/auto_deliver.done") else "no"))
PYEOF
