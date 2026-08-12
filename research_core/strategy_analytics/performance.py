from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any


def _returns(values: list[float]) -> list[float]:
    return [values[i] / values[i - 1] - 1 for i in range(1, len(values)) if values[i - 1]]


def analyze_window(curve: list[dict[str, Any]], start: str | None = None, end: str | None = None) -> dict[str, float | int | None]:
    rows = [p for p in curve if (not start or str(p["date"]) >= start) and (not end or str(p["date"]) <= end)]
    if len(rows) < 2:
        return {"observations": len(rows), "total_return": None, "annualized_return": None}
    nav = [float(p["nav"]) for p in rows]
    bench = [float(p.get("benchmark") or 1) for p in rows]
    r, br = _returns(nav), _returns(bench)
    total = nav[-1] / nav[0] - 1
    annual = (1 + total) ** (252 / max(len(r), 1)) - 1 if total > -1 else -1.0
    vol = pstdev(r) * math.sqrt(252) if len(r) > 1 else 0.0
    downside = math.sqrt(mean([min(x, 0) ** 2 for x in r])) * math.sqrt(252) if r else 0.0
    peak, max_dd = nav[0], 0.0
    for value in nav:
        peak = max(peak, value); max_dd = min(max_dd, value / peak - 1)
    covariance = mean([(x-mean(r))*(y-mean(br)) for x,y in zip(r,br)]) if r and br else 0.0
    bench_var = mean([(x-mean(br))**2 for x in br]) if br else 0.0
    beta = covariance / bench_var if bench_var else None
    residual = [x-y for x,y in zip(r,br)]
    tracking = pstdev(residual) * math.sqrt(252) if len(residual)>1 else 0.0
    return {"observations":len(rows),"total_return":total,"annualized_return":annual,"benchmark_return":bench[-1]/bench[0]-1,
            "excess_return":total-(bench[-1]/bench[0]-1),"volatility":vol,"downside_volatility":downside,
            "max_drawdown":abs(max_dd),"sharpe":mean(r)*252/vol if vol else None,"sortino":mean(r)*252/downside if downside else None,
            "calmar":annual/abs(max_dd) if max_dd else None,"beta":beta,"alpha":mean(r)*252-(beta or 0)*mean(br)*252,
            "tracking_error":tracking,"information_ratio":mean(residual)*252/tracking if tracking else None,
            "var_95":mean(r)-1.645*pstdev(r) if len(r)>1 else None,"win_rate":sum(x>0 for x in r)/len(r)}
