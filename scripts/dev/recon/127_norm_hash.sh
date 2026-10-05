REPO=/home/data/agentmatrix_run/agentmatrix
cd $REPO || exit 1
echo "=== 服务器侧 LF 归一化后的 sha256（消除行尾差异，只看内容）==="
find research_core scripts -name '*.py' -type f 2>/dev/null | sort | while read -r f; do
  h=$(tr -d '\r' < "$f" | sha256sum | cut -d' ' -f1)
  echo "$h $f"
done
echo "###END###"
