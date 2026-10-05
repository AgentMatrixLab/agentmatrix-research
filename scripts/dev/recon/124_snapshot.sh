RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
D=$RUN/rehearsal/server_snapshot
rm -rf "$D"; mkdir -p "$D"
for f in research_core/factor_lab/catalog_readiness.py \
         research_core/factor_lab/delivery_manifest.py \
         research_core/factor_lab/robustness.py \
         research_core/factor_lab/scoring.py \
         research_core/factor_lab/supplementary.py \
         research_core/factor_lab/validation_result.py \
         research_core/strategy_operations/signal_pipeline.py \
         research_core/strategy_operations/strategy_backtest.py; do
  mkdir -p "$D/$(dirname "$f")"
  cp "$REPO/$f" "$D/$f" 2>/dev/null && echo "  copied $f"
done
echo
echo "=== 这些文件各自被谁 import（判断改动是否会波及在跑的分片）==="
for m in validation_result scoring supplementary robustness catalog_readiness delivery_manifest; do
  n=$(grep -rl "$m" "$REPO/research_core/factor_lab/deterministic_validation.py" 2>/dev/null | wc -l)
  echo "  deterministic_validation.py 是否引用 $m: $n"
done
echo
echo "=== frozen 文件是否在差异清单里 ==="
grep -c 'deterministic_validation' /dev/null 2>/dev/null
ls -la "$REPO/configs/validation_gates.yaml" | sed 's/^/  /'
echo
echo "=== validation_result 被 oos 路径引用的情况 ==="
grep -rn 'validation_result' "$REPO/research_core/factor_lab/deterministic_validation.py" 2>/dev/null | head -5 | sed 's/^/  /'
grep -rn 'validation_result' "$REPO/research_core/factor_lab/cli.py" 2>/dev/null | head -5 | sed 's/^/  /'
date -Is
