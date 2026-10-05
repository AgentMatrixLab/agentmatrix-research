echo "===== users.xml 中的 password 段 ====="
grep -A3 -B3 -i "password" /etc/clickhouse-server/users.xml 2>/dev/null | head -40

echo
echo "===== daily_etl.py 里的连接代码 ====="
grep -n -i -E "clickhouse|Client\(|host=|password|user=" /home/data/daily_etl.py 2>/dev/null | head -25

echo
echo "===== 各 .env 的键名（值打码） ====="
for f in /root/.env /home/data/agentmatrix-strategy/shared/dashboard.env /home/data/cogalpha_run/cogalpha/.env; do
  echo "--- $f ---"
  sed -E "s/(=).*/\1 ****/" "$f" 2>/dev/null | head -20
done

echo
echo "===== 哪些脚本真的连过 clickhouse ====="
grep -rIn --include=*.py -E "clickhouse_connect|get_client\(|clickhouse_driver" /home/data /root --exclude-dir=.git --exclude-dir=__pycache__ 2>/dev/null | head -20
