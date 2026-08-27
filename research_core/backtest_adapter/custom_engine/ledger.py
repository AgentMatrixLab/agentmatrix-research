from __future__ import annotations
from typing import Any

def rebuild_position_ledger(transactions: list[dict[str,Any]], initial_cash: float, last_prices: dict[str,float] | None=None) -> dict[str,Any]:
    cash=float(initial_cash); positions={}; realized=0.0
    for t in sorted(transactions,key=lambda x:str(x.get("time") or x.get("date") or "")):
        symbol=str(t.get("symbol") or t.get("code") or ""); side=str(t.get("side") or "").upper(); qty=abs(float(t.get("qty",t.get("shares",0)) or 0)); price=float(t.get("price") or 0); fee=float(t.get("fee",t.get("commission",0)) or 0)
        if not symbol or not qty: continue
        p=positions.setdefault(symbol,{"quantity":0.0,"average_cost":0.0})
        if side=="BUY":
            new_qty=p["quantity"]+qty; p["average_cost"]=(p["quantity"]*p["average_cost"]+qty*price+fee)/new_qty if new_qty else 0; p["quantity"]=new_qty; cash-=qty*price+fee
        elif side=="SELL":
            sold=min(qty,p["quantity"]); realized+=sold*(price-p["average_cost"])-fee; p["quantity"]-=sold; cash+=sold*price-fee
            if p["quantity"]<=1e-12: p.update(quantity=0.0,average_cost=0.0)
    prices=last_prices or {}; rows=[]
    for symbol,p in positions.items():
        if p["quantity"]<=0: continue
        price=float(prices.get(symbol,p["average_cost"])); value=p["quantity"]*price; pnl=value-p["quantity"]*p["average_cost"]
        rows.append({"symbol":symbol,"quantity":p["quantity"],"average_cost":p["average_cost"],"last_price":price,"market_value":value,"unrealized_pnl":pnl,"unrealized_pnl_pct":pnl/(p["quantity"]*p["average_cost"]) if p["average_cost"] else None})
    equity=cash+sum(r["market_value"] for r in rows)
    for r in rows:r["weight"]=r["market_value"]/equity if equity else 0
    return {"cash":cash,"total_equity":equity,"realized_pnl":realized,"positions":rows,"source":"transaction_ledger_v1"}
