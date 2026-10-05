RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
cd $REPO || exit 1
export PYTHONPATH=$REPO
echo "=== 对真实交付目录运行验收检查（37 分片的链条产物）==="
/home/data/conda-envs/rqsdk/bin/python -X utf8 scripts/verify_delivery.py \
  --delivery-dir "$RUN/delivery"
echo
echo "  退出码 $?（1 = 有检查未通过；此处应为 1，因为只有 74 个交付因子 < 300）"
