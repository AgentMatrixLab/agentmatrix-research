for i in 000 007 008 009 010 018 019 080 099 100 208 212; do
  old=$(printf "shard%03d" "$i" 2>/dev/null || echo "<FAILED>")
  new=$(printf "shard%03d" "$((10#$i))")
  printf "  index=%s  old=%s  new=%s\n" "$i" "$old" "$new"
done
