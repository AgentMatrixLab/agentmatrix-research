echo "===== 磁盘 ====="
df -hT | grep -v -E 'tmpfs|overlay'
echo
echo "===== 块设备 ====="
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT 2>/dev/null | head -25
echo
echo "===== /root 顶层 ====="
ls -la /root/ 2>/dev/null | head -40
echo
echo "===== /home ====="
ls -la /home/ 2>/dev/null
echo
echo "===== 大目录 (顶层, >1G) ====="
du -sh /* 2>/dev/null | sort -rh | head -15
