RUN=/home/data/agentmatrix_run
D=$(ls "$RUN"/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)
P=$(ls "$RUN"/delivery/values/parts/*.parquet 2>/dev/null | wc -l)
echo "shards=$D parts=$P"
if [ -f "$RUN/logs/auto_deliver.done" ]; then
  echo "TRIGGERED: $(cat "$RUN/logs/auto_deliver.done")"
else
  echo "waiting"
fi
