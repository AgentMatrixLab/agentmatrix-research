echo "===== 找 91 候选清单 ====="
find /home/data -maxdepth 4 -name "candidate*.csv" -o -maxdepth 4 -name "*candidates*.csv" 2>/dev/null | head -10

echo
echo "===== 找产出这些文件的脚本（10/3 前后） ====="
find /home/data -maxdepth 4 -newermt "2026-10-02" -name "*.py" 2>/dev/null | head -20

echo
echo "===== agentmatrix-research-validation 仓库里的候选相关文件 ====="
find /home/data/agentmatrix-research-validation-20260925 -maxdepth 3 \( -name "candidate*" -o -name "*frozen*" -o -name "*frozen*" \) 2>/dev/null | head -15

echo
echo "===== 搜含 91 行的候选 csv ====="
for f in $(find /home/data -maxdepth 5 -name "*.csv" 2>/dev/null | head -200); do
  n=$(wc -l < "$f" 2>/dev/null)
  if [ "$n" = "92" ] || [ "$n" = "91" ]; then
    echo "$n lines: $f"
  fi
done

echo
echo "===== delivery_export 的 log / 说明 ====="
ls -la /home/data/delivery_export/
find /home/data -maxdepth 3 -newermt "2026-10-03" -name "*.log" 2>/dev/null | head -10
