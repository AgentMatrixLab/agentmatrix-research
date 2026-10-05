RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
PANEL=$RUN/panel/validation_panel.parquet
RUNS=$RUN/runtime_mirror/data/factor_lab/validation_runs
REH=$RUN/rehearsal
PARTS=$RUN/delivery/values/parts
mkdir -p "$REH"
cd "$REPO" || exit 1
export PYTHONPATH=$REPO

echo "=== 前置检查 ==="
echo "  panel sidecar: $(ls $PANEL.json 2>&1 | head -1)"
echo "  panel source : $($PY -X utf8 -c "import json;print(json.load(open('$PANEL.json'))['source'])" 2>&1 | head -1)"
echo "  留存 parts   : $(ls $PARTS/*.parquet 2>/dev/null | wc -l)"
echo "  已完成分片   : $(ls $RUN/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)"
echo "  镜像结果     : $(find $RUNS -name validation_result.json 2>/dev/null | wc -l)"
echo "  磁盘可用     : $(df -h / | awk 'NR==2{print $4}')"

echo
echo "########## 彩排 1. 合并分片 manifest ##########"
$PY -X utf8 -u scripts/merge_batch_manifests.py \
    --shards $RUN/shards/shard*/oos/batch_manifest.json \
    --candidates $RUN/candidate_list.csv \
    --output-dir "$REH/merged_oos" || { echo "MERGE FAILED"; exit 1; }

echo
echo "########## 彩排 2b. 合并因子值 parts ##########"
$PY -X utf8 -u scripts/consolidate_factor_values.py \
    --parts "$PARTS" --output "$REH/factor_values.parquet" || { echo "CONSOLIDATE FAILED"; exit 1; }

echo
echo "########## 彩排 3. 补充层（FDR + 行业中性留存）##########"
time $PY -X utf8 -u scripts/run_robustness_supplement.py \
    --runs-dir "$RUNS" \
    --panel-file "$PANEL" \
    --factor-file "$REH/factor_values.parquet" \
    --q 0.05 \
    --out "$REH/supplementary_report.json" || { echo "SUPPLEMENT FAILED"; exit 1; }

echo
echo "########## 彩排 4. 交付清单 ##########"
$PY -X utf8 -u scripts/build_delivery_manifest.py \
    --candidates $RUN/candidate_list.csv \
    --batch-manifest "$REH/merged_oos/batch_manifest.json" \
    --runs-dir "$RUNS" \
    --supplementary "$REH/supplementary_report.json" \
    --factor-file "$REH/factor_values.parquet" \
    --cluster-threshold 0.7 \
    --summary-out "$REH/delivery_manifest.summary.json" \
    --out "$REH/delivery_manifest.csv" || { echo "MANIFEST FAILED"; exit 1; }

echo
echo "########## 彩排 5a. 策略演示 ##########"
time $PY -X utf8 -u scripts/build_strategy_demos.py \
    --panel-file "$PANEL" \
    --factor-file "$REH/factor_values.parquet" \
    --runs-dir "$RUNS" \
    --out-dir "$REH/strategy_demos" || echo "DEMOS FAILED（记录 traceback 后修复）"

echo
echo "########## 彩排 5b. 实盘信号 ##########"
$PY -X utf8 -u scripts/build_live_signals.py \
    --panel-file "$PANEL" \
    --factor-file "$REH/factor_values.parquet" \
    --runs-dir "$RUNS" \
    --delivery-manifest "$REH/delivery_manifest.csv" \
    --out-dir "$REH/live_signals" || echo "SIGNALS FAILED（记录 traceback 后修复）"

echo
echo "########## 彩排产物 ##########"
ls -la "$REH"
echo
echo "--- 交付清单摘要 ---"
cat "$REH/delivery_manifest.summary.json" 2>/dev/null
echo
echo "--- 交付清单前 4 行 ---"
head -4 "$REH/delivery_manifest.csv" 2>/dev/null | cut -c1-240
date -Is
