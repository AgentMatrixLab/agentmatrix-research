#!/usr/bin/env bash
# Purge the ClickHouse password (and the server address) from local git history.
# The branch has never been pushed, so this rewrites only local objects.
set -e
cd /d/agentmatrix

git status --porcelain | head -5
echo "--- 重写前的提交数 ---"
git rev-list --count HEAD

echo "--- 备份原分支 ---"
git branch -f backup-pre-scrub HEAD 2>/dev/null || true

echo "--- 重写历史 ---"
FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --tree-filter '
  ret=0
  if [ -d scripts/dev/recon ]; then
    find scripts/dev/recon -name "*.sh" -print0 2>/dev/null | xargs -0 -r sed -i "s/<redacted>/<redacted>/g" || ret=1
  fi
  for f in scripts/prepare_server_panel.py scripts/dev/ssh_run.py scripts/dev/upload_repo.py \
           docs/delivery/2026-10-05-server-recon.md; do
    [ -f "$f" ] && sed -i "s/<redacted>/<redacted>/g; s/115\.159\.73\.134/<server-ip>/g" "$f" || true
  done
  exit 0
' -- --all

echo "--- 清理 reflog 与不可达对象 ---"
rm -rf .git/refs/original
git reflog expire --expire=now --all
git gc --prune=now --aggressive --quiet 2>/dev/null || git gc --prune=now --quiet

echo "--- 验证：全历史扫描 ---"
for pat in "<redacted>" "<server-ip>"; do
  n=$(git grep -I -F "$pat" $(git rev-list --all) 2>/dev/null | wc -l)
  echo "  $pat -> $n 处"
done
echo "--- 重写后的提交数 ---"
git rev-list --count HEAD
git log --oneline -1
