#!/usr/bin/env bash
# Everything after the shards finish, in one place.
#
# Runs on the 115 server. Each step consumes the previous step's artifact, so a
# failure stops the chain rather than producing a delivery built on half the
# evidence.
#
#   1. merge the per-shard batch manifests into one
#   2. collect factor VALUES for the passing factors -- from the retention parts if
#      the daemon caught them, otherwise by rebuilding
#   2b. consolidate those parts into one file with a sidecar
#   3. additive robustness layer (FDR badge, industry-neutral retention)
#   4a. strategy demos, which publish the clustering
#   4b. fused delivery manifest (the single authoritative table), reusing that clustering
#   5. live signals (文件单 / 条件单 / Supabase rows)
#
# Evidence lives OUTSIDE the deploy directory on purpose. The frozen config writes
# per-factor results under <repo>/data/..., and an upload used to wipe that tree, which
# silently shrinks both the tier assignment and the FDR batch. `--runs-dir` therefore
# points at the mirror.
#
# Usage:  run_downstream.sh [run_root]
set -u

RUN=${1:-/home/data/agentmatrix_run}
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
PANEL=$RUN/panel/validation_panel.parquet
CONFIG=$REPO/configs/validation_gates.yaml
OUT=$RUN/delivery
LOGS=$RUN/logs
RUNS=$RUN/runtime_mirror/data/factor_lab/validation_runs
PARTS=$OUT/values/parts
REBUILD=$OUT/rebuild
mkdir -p "$OUT" "$LOGS" "$REBUILD"

cd "$REPO" || exit 1
export PYTHONPATH="$REPO"

step() { echo; echo "########## $* ##########"; }

step "0. 检查产物是否齐全"
SHARD_DIRS=$(ls -d "$RUN"/shards/shard* 2>/dev/null | wc -l)
OOS_OK=$(ls "$RUN"/shards/shard*/oos/batch_manifest.json 2>/dev/null | wc -l)
echo "  分片目录   : $SHARD_DIRS"
echo "  oos   完成 : $OOS_OK"
echo "  留存 parts : $(ls $PARTS/*.parquet 2>/dev/null | wc -l)"
echo "  镜像 runs  : $(ls -d $RUNS/*/ 2>/dev/null | wc -l) 个因子目录"
if [ "$OOS_OK" -eq 0 ]; then
  echo "  没有任何 oos 结果，终止"
  exit 1
fi
if [ ! -d "$RUNS" ]; then
  echo "  镜像 runs 目录不存在: $RUNS"
  echo "  先跑 scripts/dev/recon/70_deploy_mirror.sh 建立镜像，否则评分与 FDR 会读到"
  echo "  部署目录里那份随时可能被覆盖的副本。"
  exit 1
fi

step "1. 合并分片 manifest"
"$PY" -X utf8 -u scripts/merge_batch_manifests.py \
    --shards "$RUN"/shards/shard*/oos/batch_manifest.json \
    --candidates "$RUN/candidate_list.csv" \
    --output-dir "$OUT/merged_oos" || { echo "MERGE FAILED"; exit 1; }

step "2. 取得通过因子的因子值"
# run_one_shard.sh deletes each shard's factor file, so the values have to come from
# somewhere. `retain_passing_values.py` already saved the passing factors' base series
# while each shard was still validating; only the shards it missed need a rebuild.
PARTS_N=$(ls $PARTS/*.parquet 2>/dev/null | wc -l)
SOURCES="$PARTS"
if [ "$PARTS_N" -gt 0 ] && [ "$PARTS_N" -ge "$OOS_OK" ]; then
  echo "  留存覆盖全部 $OOS_OK 个已完成分片，无需重建"
elif [ "$PARTS_N" -gt 0 ]; then
  # Partial retention. The rebuild covers EVERY passing factor, not just the missing ones, so
  # on success it replaces the parts rather than being merged with them -- concatenating both
  # would write most factors twice and duplicate every (date, code, factor_name) key.
  echo "  留存只有 $PARTS_N / $OOS_OK 个分片；重建全部通过因子以补齐"
  if "$PY" -X utf8 -u scripts/rebuild_passing_factors.py \
      --batch-manifest "$OUT/merged_oos/batch_manifest.json" \
      --candidates "$RUN/candidate_list.csv" \
      --panel-file "$PANEL" \
      --config "$CONFIG" \
      --output-dir "$REBUILD"; then
    SOURCES="$REBUILD/factor_values.parquet"
    echo "  因子值来源: 重建文件（覆盖全部通过因子）"
  else
    SOURCES="$PARTS"
    echo "  REBUILD FAILED -- 仅用留存 parts（覆盖不完整，交付清单会把缺失因子显示为空）"
  fi
else
  echo "  没有留存 parts；回退到重建全部通过因子"
  "$PY" -X utf8 -u scripts/rebuild_passing_factors.py \
      --batch-manifest "$OUT/merged_oos/batch_manifest.json" \
      --candidates "$RUN/candidate_list.csv" \
      --panel-file "$PANEL" \
      --config "$CONFIG" \
      --output-dir "$REBUILD" || { echo "REBUILD FAILED"; exit 1; }
  SOURCES="$REBUILD/factor_values.parquet"
fi

step "2b. 合并为单一因子值文件（demo 与 cross_check 都要求带 sidecar 的单文件）"
# The retention daemon produces one part per shard; the strategy demo refuses to run without
# a sibling <factor-file>.json sidecar, and the cross-check verifies a digest against a named
# file. Consolidating is a row-group copy -- bounded in memory, unlike a rebuild.
CONSOLIDATED=$REBUILD/factor_values.parquet
# shellcheck disable=SC2086
"$PY" -X utf8 -u scripts/consolidate_factor_values.py \
    --parts $SOURCES --output "$CONSOLIDATED" || { echo "CONSOLIDATE FAILED"; exit 1; }
VALUES=$CONSOLIDATED
echo "  因子值来源: $VALUES"

step "3. 稳健性附加层（FDR 勋章 + 行业中性留存）"
# ~21 s per factor single-threaded, measured on the real panel, so hundreds of factors is
# hours on the critical path. The maths is GIL-bound and embarrassingly parallel; fork shares
# the ~3 GB panel. Measured on 29 real factors: 612 s serial vs 269 s at jobs=6, identical
# numbers. 6 leaves the box room for the rest of the chain.
"$PY" -X utf8 -u scripts/run_robustness_supplement.py \
    --runs-dir "$RUNS" \
    --panel-file "$PANEL" \
    --factor-file "$VALUES" \
    --q 0.05 \
    --jobs "${NEUTRAL_JOBS:-6}" \
    --out "$OUT/supplementary_report.json" || { echo "SUPPLEMENT FAILED"; exit 1; }

step "4a. 策略演示（样本外，含低位相关核心集）"
# Runs BEFORE the manifest on purpose. It builds the ranked block and publishes its clustering
# to clusters.json, which the manifest then reuses: the delivery table's cluster_id and the
# low-correlation core the demo traded then come from one clustering instead of two, and the
# manifest does not rebuild an ~18 GB block purely to re-derive the correlation.
"$PY" -X utf8 -u scripts/build_strategy_demos.py \
    --panel-file "$PANEL" \
    --factor-file "$VALUES" \
    --runs-dir "$RUNS" \
    --out-dir "$OUT/strategy_demos" || { echo "DEMOS FAILED"; exit 1; }

step "4b. 交付清单（25 列冻结 schema）"
CLUSTERS="$OUT/strategy_demos/clusters.json"
CLUSTER_ARG=""
if [ -f "$CLUSTERS" ]; then
  CLUSTER_ARG="--clusters-json $CLUSTERS"
  echo "  复用演示步骤发布的聚类: $CLUSTERS"
else
  echo "  未找到 clusters.json；交付清单将自行计算聚类（会多花一次全表读取）"
fi
"$PY" -X utf8 -u scripts/build_delivery_manifest.py \
    --candidates "$RUN/candidate_list.csv" \
    --batch-manifest "$OUT/merged_oos/batch_manifest.json" \
    --runs-dir "$RUNS" \
    --supplementary "$OUT/supplementary_report.json" \
    --factor-file "$VALUES" \
    --cluster-threshold 0.7 \
    $CLUSTER_ARG \
    --out "$OUT/delivery_manifest.csv" || { echo "MANIFEST FAILED"; exit 1; }

step "5. 实盘信号（文件单 / 条件单 / Supabase 行）"
"$PY" -X utf8 -u scripts/build_live_signals.py \
    --panel-file "$PANEL" \
    --factor-file "$VALUES" \
    --runs-dir "$RUNS" \
    --delivery-manifest "$OUT/delivery_manifest.csv" \
    --out-dir "$OUT/live_signals" || { echo "SIGNALS FAILED"; exit 1; }

echo
echo "########## 完成 ##########"
echo "产物在 $OUT"
ls -la "$OUT"
