RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
echo "=== 服务器上的 delivery_manifest.py 是哪一版？ ==="
echo "  in_delivery_package_tier_sa 出现次数: $(grep -c 'in_delivery_package_tier_sa' $REPO/research_core/factor_lab/delivery_manifest.py 2>/dev/null)"
echo "  PACKAGE_TIERS 是否仍用于进包判断:"
grep -n 'in_delivery_package' $REPO/research_core/factor_lab/delivery_manifest.py | sed 's/^/    /'
echo
echo "  与本地版本对比:"
python - <<'PYEOF' 2>/dev/null || true
PYEOF
echo "  本地文件 sha256:"
sha256sum "$REPO/research_core/factor_lab/delivery_manifest.py" 2>/dev/null | sed 's/^/    /'
echo
echo "=== 本地版本（应为新口径）==="
echo "  （下面的行来自本地仓库的同一文件）"
date -Is
