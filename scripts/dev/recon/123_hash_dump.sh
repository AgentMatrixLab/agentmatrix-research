REPO=/home/data/agentmatrix_run/agentmatrix
cd $REPO || exit 1
echo "=== 服务器侧 research_core + scripts 的 sha256（用于与本地逐文件比对）==="
find research_core scripts -name '*.py' -type f 2>/dev/null | sort | while read -r f; do
  sha256sum "$f"
done
echo "###END###"
