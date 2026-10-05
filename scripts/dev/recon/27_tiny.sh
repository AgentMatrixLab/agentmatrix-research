cd /home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
RUN=/home/data/agentmatrix_run
export PYTHONPATH=$RUN/agentmatrix
mkdir -p $RUN/logs

# 3 因子，与 pilot 同族但不同条目，测优化后的内存与速度
head -1 $RUN/candidate_list.csv > $RUN/tiny_candidates.csv
sed -n '2p;100p;300p' $RUN/candidate_list.csv >> $RUN/tiny_candidates.csv
echo "样本: $(tail -n +2 $RUN/tiny_candidates.csv | cut -d, -f1 | tr '\n' ' ')"

echo
echo "===== 优化后：3 因子计时 ====="
/usr/bin/time -v $PY -X utf8 -u scripts/build_factor_values.py \
    --candidates $RUN/tiny_candidates.csv \
    --panel-file $RUN/panel/validation_panel.parquet \
    --config configs/validation_gates.yaml \
    --output $RUN/tiny/factor_values.parquet \
    --report $RUN/tiny/report.json 2>&1 | grep -E "panel columns|candidates|panel:|rows |series|秒|s/factor|Elapsed \(wall|Maximum resident|FAIL" | head -15

echo
echo "===== 产物 ====="
ls -la $RUN/tiny/ 2>/dev/null
echo
echo "===== 磁盘 / 内存 ====="
df -h / | tail -1
free -g | head -2
