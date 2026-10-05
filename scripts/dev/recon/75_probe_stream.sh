REPO=/home/data/agentmatrix_run/agentmatrix
PY=/home/data/conda-envs/rqsdk/bin/python
export PYTHONPATH=$REPO
cd $REPO || exit 1

echo "=== 1. 真实留存 parts 上的流式读取验证 ==="
$PY -X utf8 - <<'PYEOF'
import sys, glob, time
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
from research_core.factor_lab.factor_value_stream import iter_factor_series, RowOrderReference

parts = sorted(glob.glob("/home/data/agentmatrix_run/delivery/values/parts/*.parquet"))
print("  parts:", len(parts))
t0 = time.time()
ids, rows = [], []
ref = RowOrderReference()
for series in iter_factor_series(parts, reference=ref):
    ids.append(series.factor_id)
    rows.append(len(series))
    print("    %-26s rows=%s  %s..%s" % (
        series.factor_id, format(len(series), ","),
        str(series.dates[0].as_py())[:10], str(series.dates[-1].as_py())[:10]))
elapsed = time.time() - t0
print("  读取 %d 个序列, %.1fs, 行序校验 %d 次" % (len(ids), elapsed, ref.comparisons))
if rows:
    print("  每个序列行数一致:", len(set(rows)) == 1, "->", format(rows[0], ","))
    per = elapsed / max(len(ids), 1)
    print("  单序列 %.2fs -> 450 序列约 %.1f 分钟" % (per, 450 * per / 60))
PYEOF

echo
echo "=== 2. 真实规模下的面板对齐 + 行业中性留存（这是最可能出错的一步）==="
$PY -X utf8 - <<'PYEOF'
import sys, glob, time, json
sys.path.insert(0, "/home/data/agentmatrix_run/agentmatrix")
from research_core.factor_lab.streaming_supplement import (
    neutral_retention_by_factor, prepare_panel,
)

parts = sorted(glob.glob("/home/data/agentmatrix_run/delivery/values/parts/*.parquet"))
panel = "/home/data/agentmatrix_run/panel/validation_panel.parquet"

t0 = time.time()
prepared = prepare_panel(panel, horizon=10)
print("  panel 准备: %s 行, %.1fs" % (format(len(prepared), ","), time.time() - t0))

t0 = time.time()
out = neutral_retention_by_factor(
    parts, panel_path=panel, horizon=10, factor_ids=None,
)
print("  留存计算完毕: %d 个因子, %.1fs" % (len(out), time.time() - t0))
for fid, value in sorted(out.items()):
    if value is None:
        print("    %-26s retention=None" % fid)
    else:
        print("    %-26s retention=%7.4f  raw_ic=%7.4f  neutral_ic=%7.4f  days=%d ind=%d" % (
            fid, value["retention"], value["raw"]["mean"], value["neutral"]["mean"],
            value["neutral"]["days"], value["industries"]))
PYEOF
date -Is
