REPO=/home/data/agentmatrix_run/agentmatrix
cd $REPO || exit 1
echo "=== verify_delivery 的实际调用（应恰好 1 处）==="
grep -n '"\$PY" -X utf8 "\$REPO/scripts/verify_delivery.py"' scripts/dev/auto_deliver.sh | sed 's/^/  /'
echo "  调用数: $(grep -c '"\$PY" -X utf8 "\$REPO/scripts/verify_delivery.py"' scripts/dev/auto_deliver.sh)"
echo
echo "=== 验收块必须出现在 DONE_MARK 之前 ==="
A=$(grep -n 'acceptance=\$?' scripts/dev/auto_deliver.sh | head -1 | cut -d: -f1)
D=$(grep -n 'acceptance_exit=\$acceptance in_delivery_package' scripts/dev/auto_deliver.sh | head -1 | cut -d: -f1)
echo "  验收行 $A  <  DONE_MARK 行 $D  →  $([ "$A" -lt "$D" ] && echo 正确 || echo '** 顺序错误 **')"
echo
echo "=== DONE_MARK 会记录的内容（模板）==="
grep -o 'chain_exit=\$status acceptance_exit=\$acceptance [a-z_]*' scripts/dev/auto_deliver.sh | sed 's/^/  /'
echo
echo "=== 运行态 ==="
echo "  auto_deliver: $(ps -eo args | awk '/auto_deliver\.sh --run/ && !/awk/ {c++} END {print c+0}')  阈值: $(grep -o 'threshold=[0-9]*' /home/data/agentmatrix_run/logs/auto_deliver.log | head -1)"
date -Is
