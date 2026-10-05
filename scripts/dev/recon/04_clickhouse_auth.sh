echo "===== ClickHouse 用户配置 ====="
ls -la /etc/clickhouse-server/users.d/ 2>/dev/null
echo "--- default-password.xml ---"
cat /etc/clickhouse-server/users.d/*.xml 2>/dev/null | head -40

echo
echo "===== 谁在用 clickhouse (进程参数 / 环境) ====="
ps aux | grep -i clickhouse | grep -v grep | head -3

echo
echo "===== 项目里出现的 clickhouse 连接串 ====="
grep -rIl --include=*.py --include=*.env --include=*.yml --include=*.yaml --include=*.json \
     -E "clickhouse|CK_HOST|CLICKHOUSE" /home/data/*.py /home/data/.env /root/.env 2>/dev/null | head -20

echo
echo "--- 提取含密码的行（仅显示键名，值打码） ---"
grep -rIh --include=*.py --include=*.env --include=*.yml --include=*.yaml \
     -E "(clickhouse|CK_|CLICKHOUSE).*(password|passwd|pwd)" \
     /home/data/ /root/ 2>/dev/null | head -12 | sed -E "s/(=|:)[[:space:]]*['\"]?[^'\"[:space:]]+/\1 ****/g"

echo
echo "===== .env 文件位置 ====="
find /home/data /root /opt -maxdepth 3 -name ".env" -o -maxdepth 3 -name "*.env" 2>/dev/null | head -15
