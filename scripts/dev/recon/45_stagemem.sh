#!/usr/bin/env bash
cd /home/data/agentmatrix_run/agentmatrix || exit 1
export PYTHONPATH=/home/data/agentmatrix_run/agentmatrix

cat > /tmp/stage_mem.py <<'PYEOF'
"""Report RSS after each stage of the load, to find where 15 GB actually goes."""
import os, sys, gc

def rss_gb():
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024 / 1024
    return float("nan")

def show(stage):
    gc.collect()
    print(f"{stage:<44} RSS={rss_gb():6.2f} GB", flush=True)

import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd

path = sys.argv[1]
show("start")

table = pq.read_table(path)
for name in ("code", "factor_name"):
    i = table.schema.get_field_index(name)
    if i >= 0 and not pa.types.is_dictionary(table.column(i).type):
        table = table.set_column(i, name, table.column(i).dictionary_encode())
show(f"arrow table read+encoded rows={table.num_rows:,}")

frame = table.to_pandas()
show("to_pandas")

del table
show("arrow table released")

frame["date"] = pd.to_datetime(frame["date"])
show("date normalised")

numeric = frame["value"].to_numpy(dtype="float64", na_value=float("nan"))
show("value to float64")

non_null = ~pd.isna(numeric)
show("non_null mask")

is_finite = __import__("numpy").isfinite(numeric[non_null]).all()
show("finite check")

del non_null, numeric
gc.collect()
show("masks released")

dupes = frame.duplicated(["date", "code", "factor_name"])
show("duplicated() built")

print("any duplicated:", bool(dupes.any()))
del dupes
show("after any()")

groups = list(frame.groupby("factor_name", sort=True, observed=True))
show(f"groupby materialised {len(groups)} groups")

series = {}
for name, group in groups:
    series[str(name)] = pd.Series(
        group["value"].to_numpy(dtype="float64"),
        index=pd.MultiIndex.from_arrays(
            [group["date"].to_numpy(), group["code"].array], names=["date", "code"]
        ),
    )
show(f"series built n={len(series)}")

print("total rows:", sum(len(s) for s in series.values()))
print("frame bytes:", frame.memory_usage(deep=True).sum() / 1e9, "GB")
PYEOF

/usr/bin/time -v /home/data/conda-envs/rqsdk/bin/python -X utf8 /tmp/stage_mem.py \
    /home/data/agentmatrix_run/memtest/factor_values.parquet 2>&1 \
  | grep -E "RSS=|rows:|duplicated|frame bytes|series built|Maximum resident"
