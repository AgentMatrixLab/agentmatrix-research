RUN=/home/data/agentmatrix_run
OUT=$RUN/rehearsal/reconcile_check.log
cat > "$RUN/rehearsal/reconcile_check.sh" <<'EOF'
#!/usr/bin/env bash
RUN=/home/data/agentmatrix_run
REPO=$RUN/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
SIG=$RUN/rehearsal/live_signals
W=$RUN/rehearsal/reconcile_check
rm -rf "$W"; mkdir -p "$W"
cd $REPO || exit 1
export PYTHONPATH=$REPO
echo "start $(date -Is)"
echo "  真实交付信号: $SIG/file_orders.csv（$(wc -l < $SIG/file_orders.csv) 行）"

echo
echo "########## 1. 客户按文件单全部成交（价格略有偏差）→ 应为「无偏差」##########"
$PY -X utf8 -u - "$SIG/file_orders.csv" "$W/fills_clean.csv" <<'PYEOF'
import csv, sys
src, dst = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
with open(dst, "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh); w.writerow(["code", "shares", "price", "side"])
    for r in rows:
        px = float(r["reference_price"]) * (1.0005 if r["side"] == "buy" else 0.9995)
        w.writerow([r["code"], r["shares"], round(px, 4), r["side"]])
print("  生成 %d 条成交（每笔都成交，价格偏离 5bp）" % len(rows))
PYEOF
$PY -X utf8 -u scripts/reconcile_signals.py \
  --orders "$SIG/file_orders.csv" --fills "$W/fills_clean.csv" \
  --out-dir "$W/clean" --slippage-warn-bps 20 > "$W/clean.out" 2>&1
echo "  exit=$?（0 = 无偏差）"
grep -E 'fill ratio|clean|结论' "$W/clean.out" | sed 's/^/    /'

echo
echo "########## 2. 客户漏单 + 部分成交 + 超预期成交 → 应报出四类偏差 ##########"
$PY -X utf8 -u - "$SIG/file_orders.csv" "$W/fills_partial.csv" <<'PYEOF'
import csv, sys
src, dst = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
with open(dst, "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh); w.writerow(["code", "shares", "price", "side"])
    for index, r in enumerate(rows):
        if index == 0:
            continue                                    # 漏掉第一笔
        shares = int(r["shares"])
        if index == 1:
            shares = max(1, shares // 2)                # 部分成交
        px = float(r["reference_price"])
        if index == 2:
            px *= 1.05 if r["side"] == "buy" else 0.95  # 明显滑点
        w.writerow([r["code"], shares, round(px, 4), r["side"]])
    w.writerow(["999999.XSHG", 100, 8.0, "buy"])        # 凭空多出的一笔
print("  生成 %d 条成交（漏 1 笔、1 笔减半、1 笔滑点 5%%、多 1 笔）" % (len(rows) + 1))
PYEOF
$PY -X utf8 -u scripts/reconcile_signals.py \
  --orders "$SIG/file_orders.csv" --fills "$W/fills_partial.csv" \
  --out-dir "$W/partial" --slippage-warn-bps 20 > "$W/partial.out" 2>&1
echo "  exit=$?（5 = 发现偏差）"
grep -E 'intended orders|fill ratio|clean|missing|unexpected|quantity breaks|price slippage|结论' "$W/partial.out" | sed 's/^/    /'

echo
echo "########## 3. 产物 ##########"
ls -la "$W/clean" "$W/partial" 2>/dev/null | sed 's/^/  /'
echo
echo "--- 偏差报告 markdown（前 22 行）---"
head -22 "$W/partial/deviation_report.md" 2>/dev/null | sed 's/^/  /'
echo "done $(date -Is)"
EOF
sed -i 's/\r$//' "$RUN/rehearsal/reconcile_check.sh"
chmod +x "$RUN/rehearsal/reconcile_check.sh"
setsid nohup bash "$RUN/rehearsal/reconcile_check.sh" > "$OUT" 2>&1 < /dev/null &
echo "  已启动（detached）"
date -Is
