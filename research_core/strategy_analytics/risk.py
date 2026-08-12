from __future__ import annotations
from typing import Any

DEFAULT_RULES = {"max_drawdown": 0.20, "volatility": 0.30, "top1_weight": 0.20, "top5_weight": 0.60, "turnover": 5.0, "gross_exposure": 1.05}

def evaluate_risk_rules(metrics: dict[str, Any], positions: list[dict[str, Any]], exposures: dict[str, Any] | None = None, rules: dict[str,float] | None = None) -> list[dict[str,Any]]:
    limits={**DEFAULT_RULES,**(rules or {})}; weights=sorted((abs(float(p.get("weight") or 0)) for p in positions),reverse=True)
    values={"max_drawdown":abs(float(metrics.get("max_drawdown") or 0)),"volatility":float(metrics.get("volatility") or 0),"turnover":float(metrics.get("turnover") or 0),"top1_weight":weights[0] if weights else 0,"top5_weight":sum(weights[:5]),"gross_exposure":float((exposures or {}).get("gross") or sum(weights))}
    return [{"id":key,"rule":key,"threshold":limit,"current":values[key],"triggered":values[key]>limit,"enabled":True} for key,limit in limits.items()]
