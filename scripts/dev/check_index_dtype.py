"""Quick local check: does the series index keep its categorical level?"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

# Build a tiny factor file with the same shape the loader expects.
rows = 200_000
codes = pd.Categorical(np.tile([f"{i:06d}.XSHE" for i in range(2000)], 100))
frame = pd.DataFrame({
    "date": pd.to_datetime(np.repeat(pd.bdate_range("2024-01-01", periods=100), 2000)),
    "code": codes,
    "factor_name": pd.Categorical(["F"] * rows),
    "value": np.random.default_rng(0).normal(size=rows),
})
print("frame bytes:", frame.memory_usage(deep=True).sum())

mi = pd.MultiIndex.from_arrays(
    [frame["date"].to_numpy(), frame["code"].array], names=["date", "code"]
)
print("level dtypes:", list(mi.dtypes))
print("index bytes:", mi.memory_usage(deep=True))
print("lookup by string works:", mi.get_level_values("code")[0])
print("isin works:", bool((mi.get_level_values("code") == "000001.XSHE").any()))
