"""Qlib IC evaluation for registered factors.

Requires Qlib 0.1.dev1+ and cn_data downloaded.
Gracefully exits when Qlib unavailable.
"""
import sys, os
import numpy as np
import pandas as pd

try:
    import qlib
    from qlib.data import D
    QLIB_AVAILABLE = True
except ImportError:
    QLIB_AVAILABLE = False


def evaluate_ic(
    expression: str,
    start_time: str = "2020-01-01",
    end_time: str = "2024-12-31",
    freq: str = "day",
    universe: str = "csi300",
) -> dict:
    """Evaluate Rank IC of a factor expression on CSI 300 using Qlib."""
    if not QLIB_AVAILABLE:
        return {"error": "Qlib not installed. Install: pip install qlib"}
    try:
        from qlib.data.dataset import DatasetH
        from qlib.data.dataset.handler import DataHandlerLP
        instruments = D.instruments(universe, start_time=start_time, end_time=end_time)
        handler = DataHandlerLP(
            instruments=instruments,
            start_time=start_time,
            end_time=end_time,
            freq=freq,
            infer_processors=[{"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature"}}],
        )
        dataset = DatasetH(handler=handler, segments={"test": (start_time, end_time)})
        df = dataset.prepare("test")
        if df.empty:
            return {"error": "No data returned from Qlib"}
        factor = df.groupby("instrument")[expression].transform(lambda x: x)
        forward_return = df.groupby("instrument")["Ref($close, -2) / $close - 1"].transform(lambda x: x.shift(-1))
        ic = factor.corr(forward_return, method="spearman")
        return {"rank_ic": float(ic), "universe": universe, "start": start_time, "end": end_time}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    if not QLIB_AVAILABLE:
        print("Qlib not installed. This script requires Qlib and cn_data.")
        print("Install: pip install qlib && python -m qlib.run.get_data qlib_data --region cn")
        sys.exit(0)
    expr = sys.argv[1] if len(sys.argv) > 1 else "Ref($close,20)/$close-1"
    result = evaluate_ic(expr)
    print(result)
