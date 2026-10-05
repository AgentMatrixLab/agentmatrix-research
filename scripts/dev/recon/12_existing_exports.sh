echo "===== ch_client.py 的连接配置 ====="
sed -n '1,40p' /home/data/quant_api_v2/ch_client.py

echo
echo "===== delivery_export 侧车文件 ====="
for f in /home/data/delivery_export/*.json; do
  echo "---------- $f ----------"
  cat "$f"
  echo
done

echo
echo "===== 这些导出是谁做的（owner/时间） ====="
stat -c '%n | %U:%G | %y' /home/data/delivery_export/* 2>/dev/null
