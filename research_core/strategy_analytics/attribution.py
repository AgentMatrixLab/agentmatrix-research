from __future__ import annotations
from typing import Any

def attribute_sub_strategies(trades: list[dict[str,Any]]) -> dict[str,Any]:
    tagged=[t for t in trades if t.get("sub_strategy")]
    if not tagged: return {"available":False,"reason":"historic trades have no sub_strategy tag","buckets":[]}
    buckets={}
    for t in tagged:
        key=str(t["sub_strategy"]); buckets[key]=buckets.get(key,0.0)+float(t.get("realized_pnl") or 0)-float(t.get("commission") or 0)
    total=sum(buckets.values())
    return {"available":True,"methodology":"tagged_trade_realized_pnl_v1","buckets":[{"name":k,"contribution":v,"contribution_pct":v/total if total else None} for k,v in buckets.items()]}
