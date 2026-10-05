echo "===== 搜 clickhouse 密码（排除库文件） ====="
grep -rIn --include=*.py --include=*.sh --include=*.md --include=*.txt --include=*.json --include=*.yaml --include=*.yml --include=*.env \
  -iE "clickhouse.{0,80}(password|passwd|pwd)|(CK|CH)_(PASS|PASSWORD|PWD)" \
  /home/data /root /opt 2>/dev/null | grep -v -E "site-packages|node_modules|\.conda|conda-envs" | head -25

echo
echo "===== 搜连接串 host:9000 / :8123 ====="
grep -rIn --include=*.py --include=*.sh --include=*.md \
  -E "(127\.0\.0\.1|localhost):(9000|8123)" /home/data /root /opt 2>/dev/null \
  | grep -v -E "site-packages|node_modules|\.conda|conda-envs" | head -20

echo
echo "===== RQdata_jobs 目录 ====="
ls -la /home/data/RQdata_jobs/ 2>/dev/null
find /home/data/RQdata_jobs -maxdepth 2 -type f -name "*.py" 2>/dev/null | head -20

echo
echo "===== delivery_export 目录（10/3 新建） ====="
ls -laR /home/data/delivery_export/ 2>/dev/null | head -40

echo
echo "===== 剩余的 access 定义 ====="
cat /var/lib/clickhouse/access/d84541ca-b051-814d-9ad1-0b3b32b5418a.sql 2>/dev/null
echo "--- users.list ---"
cat /var/lib/clickhouse/access/users.list 2>/dev/null
echo "--- roles.list ---"
cat /var/lib/clickhouse/access/roles.list 2>/dev/null
