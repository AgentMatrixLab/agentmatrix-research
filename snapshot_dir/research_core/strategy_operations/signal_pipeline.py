"""Daily signal generation, order export and execution reconciliation.

This is the last mile the client asked for: concrete tradable output, delivered in
a form a 文件单 / 条件单 can consume directly or that can be pushed to Supabase for
a local QMT / 掘金量化 account, plus a偏差 report comparing what we intended with
what actually filled.

The module is deliberately pure: it turns weights into orders, orders into
files, and intent-versus-fill into a deviation report. It performs no I/O beyond
the explicit exporters and never touches a broker API, so every rule here is
testable offline and reviewable line by line.

Four stages, each usable on its own:

``build_targets``        scores -> target weights with caps and a lot-size floor
``diff_positions``       previous holdings -> the orders needed to get there
``write_*``              order objects -> 文件单 CSV / 条件单 JSON / Supabase rows
``reconcile_execution``  intended orders vs actual fills -> deviations and verdict

Rounding is always conservative: a position that would round to fewer than one
lot is dropped rather than rounded up, because over-ordering is a real-money
error while missing a marginal name is not.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "DeviationReport",
    "Order",
    "SignalError",
    "TargetPosition",
    "build_targets",
    "diff_positions",
    "reconcile_execution",
    "to_conditional_orders",
    "to_supabase_rows",
    "write_conditional_orders",
    "write_file_orders",
]

CN_TZ = timezone(timedelta(hours=8))

#: A-share round lot. Orders are always whole lots.
LOT_SIZE = 100


class SignalError(ValueError):
    """Raised when a signal cannot be built or exported under the stated rules."""


# ── data shapes ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TargetPosition:
    code: str
    weight: float
    shares: int
    reference_price: float
    score: float = 0.0

    @property
    def notional(self) -> float:
        return self.shares * self.reference_price


@dataclass(frozen=True)
class Order:
    code: str
    side: str          # "buy" or "sell"
    shares: int        # always a positive whole number of shares
    reference_price: float
    target_weight: float
    current_weight: float
    reason: str

    @property
    def notional(self) -> float:
        return self.shares * self.reference_price


# ── stage 1: scores to targets ──────────────────────────────────────────

def build_targets(
    scores: Mapping[str, float] | pd.Series,
    *,
    total_value: float,
    prices: Mapping[str, float],
    top_n: int = 50,
    weighting: str = "equal",
    max_weight: float = 0.05,
    min_weight: float = 0.0,
) -> list[TargetPosition]:
    """Turn factor scores into capped, lot-rounded target positions.

    ``weighting`` is ``equal`` or ``score`` (proportional to the score's
    cross-sectional rank, which is robust to outliers). Weights are capped at
    ``max_weight`` and the excess is redistributed once, then positions below
    ``min_weight`` are dropped.
    """
    if total_value <= 0:
        raise SignalError(f"total_value must be positive, got {total_value!r}")
    if top_n < 1:
        raise SignalError(f"top_n must be at least 1, got {top_n!r}")
    if not 0 < max_weight <= 1:
        raise SignalError(f"max_weight must lie in (0, 1], got {max_weight!r}")
    if weighting not in ("equal", "score"):
        raise SignalError(f"weighting must be 'equal' or 'score', got {weighting!r}")

    series = pd.Series(dict(scores), dtype=float).dropna()
    if series.empty:
        raise SignalError("no scores were supplied")

    # Highest score first; ties broken by code so the basket is deterministic.
    ranked = series.sort_values(ascending=False, kind="stable")
    ranked = ranked.iloc[:top_n]

    selected = [code for code in ranked.index if code in prices and prices[code] > 0]
    dropped = sorted(set(ranked.index) - set(selected))
    if not selected:
        raise SignalError("none of the selected codes has a usable price")
    if dropped:
        # Not fatal, but the caller must know the basket shrank.
        pass

    if weighting == "equal":
        raw = pd.Series(1.0, index=selected)
    else:
        # Rank within the selection, so a single extreme score cannot dominate.
        raw = pd.Series(
            np.arange(len(selected), 0, -1, dtype=float), index=selected
        )
    weights = raw / raw.sum()

    capped = weights.clip(upper=max_weight)
    shortfall = 1.0 - float(capped.sum())
    if shortfall > 1e-9:
        room = (max_weight - capped).clip(lower=0.0)
        if float(room.sum()) > 0:
            capped = capped + room * (shortfall / float(room.sum()))
    weights = capped / float(capped.sum())

    positions: list[TargetPosition] = []
    for code in selected:
        weight = float(weights[code])
        if weight < min_weight:
            continue
        price = float(prices[code])
        lots = math.floor(total_value * weight / (price * LOT_SIZE))
        shares = lots * LOT_SIZE
        if shares <= 0:
            # Rounding down to zero lots means the name is too small to hold;
            # dropping it is correct, rounding up would over-order.
            continue
        positions.append(
            TargetPosition(
                code=code,
                weight=weight,
                shares=shares,
                reference_price=price,
                score=float(series.get(code, 0.0)),
            )
        )

    if not positions:
        raise SignalError(
            "every target rounded below one lot; increase total_value or relax min_weight"
        )
    positions.sort(key=lambda item: (-item.weight, item.code))
    return positions


# ── stage 2: holdings to orders ─────────────────────────────────────────

def diff_positions(
    targets: Sequence[TargetPosition],
    holdings: Mapping[str, int] | None,
    *,
    total_value: float,
    prices: Mapping[str, float] | None = None,
) -> list[Order]:
    """Orders required to move current holdings onto the target basket.

    Everything not in the target basket is sold, which is what makes this a
    full-rebalance rather than an incremental add.
    """
    current = dict(holdings or {})
    price_of = dict(prices or {})
    for position in targets:
        price_of.setdefault(position.code, position.reference_price)

    orders: list[Order] = []
    target_codes = {position.code for position in targets}

    for position in targets:
        held = int(current.get(position.code, 0))
        delta = position.shares - held
        if delta == 0:
            continue
        orders.append(
            Order(
                code=position.code,
                side="buy" if delta > 0 else "sell",
                shares=abs(delta),
                reference_price=position.reference_price,
                target_weight=position.weight,
                current_weight=_weight_of(held, price_of.get(position.code), total_value),
                reason="rebalance_to_target",
            )
        )

    for code in sorted(set(current) - target_codes):
        held = int(current[code])
        if held == 0:
            continue
        price = price_of.get(code)
        if price is None or price <= 0:
            raise SignalError(
                f"{code} is held but has no usable price; refusing to emit a sell "
                "order at an unknown price"
            )
        orders.append(
            Order(
                code=code,
                side="sell",
                shares=held,
                reference_price=float(price),
                target_weight=0.0,
                current_weight=_weight_of(held, price, total_value),
                reason="exit_not_in_target",
            )
        )

    orders.sort(key=lambda item: (item.side != "sell", -item.notional, item.code))
    return orders


def _weight_of(shares: int, price: float | None, total_value: float) -> float:
    if not price or total_value <= 0:
        return 0.0
    return float(shares) * float(price) / float(total_value)


# ── stage 3: exports ────────────────────────────────────────────────────

FILE_ORDER_COLUMNS = (
    "code",
    "side",
    "shares",
    "price_type",
    "reference_price",
    "target_weight",
    "reason",
)


def write_file_orders(
    orders: Sequence[Order],
    path: str | Path,
    *,
    price_type: str = "limit",
    extra: Mapping[str, Any] | None = None,
) -> Path:
    """Write a 文件单 CSV.

    ``price_type`` is emitted verbatim so the receiving QMT/掘金 template decides
    how to interpret the reference price; we do not silently turn a limit order
    into a market order.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    columns = list(FILE_ORDER_COLUMNS) + sorted(extra or {})
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for order in orders:
            row = {
                "code": order.code,
                "side": order.side,
                "shares": order.shares,
                "price_type": price_type,
                "reference_price": f"{order.reference_price:.4f}",
                "target_weight": f"{order.target_weight:.6f}",
                "reason": order.reason,
            }
            row.update(extra or {})
            writer.writerow(row)
    return target


def to_conditional_orders(
    orders: Sequence[Order],
    *,
    strategy_id: str,
    trade_date: str,
    price_offset_bps: float = 0.0,
) -> list[dict[str, Any]]:
    """Conditional-order payloads: trigger on the reference price plus an offset.

    A buy triggers when the price falls to the reference less the offset; a sell
    when it rises to the reference plus the offset. Emitting the trigger price
    explicitly is what lets the receiving platform run unattended.
    """
    payload: list[dict[str, Any]] = []
    for order in orders:
        offset = order.reference_price * price_offset_bps / 10_000.0
        trigger = (
            order.reference_price - offset if order.side == "buy" else order.reference_price + offset
        )
        payload.append(
            {
                "strategy_id": strategy_id,
                "trade_date": trade_date,
                "code": order.code,
                "side": order.side,
                "volume": order.shares,
                "price_type": "limit",
                "trigger_price": round(trigger, 4),
                "reference_price": round(order.reference_price, 4),
                "target_weight": round(order.target_weight, 6),
                "reason": order.reason,
            }
        )
    return payload


def write_conditional_orders(
    orders: Sequence[Order],
    path: str | Path,
    *,
    strategy_id: str,
    trade_date: str,
    price_offset_bps: float = 0.0,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = to_conditional_orders(
        orders,
        strategy_id=strategy_id,
        trade_date=trade_date,
        price_offset_bps=price_offset_bps,
    )
    target.write_text(
        json.dumps(
            {
                "strategy_id": strategy_id,
                "trade_date": trade_date,
                "generated_at": datetime.now(CN_TZ).isoformat(timespec="seconds"),
                "orders": payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def to_supabase_rows(
    orders: Sequence[Order],
    *,
    strategy_id: str,
    trade_date: str,
    portfolio_value: float,
    price_offset_bps: float = 0.0,
    signal_batch: str | None = None,
) -> list[dict[str, Any]]:
    """Rows for the Supabase signal table read by the local execution account.

    The column set is flat and stable so an upsert keyed on
    ``(strategy_id, trade_date, code)`` is idempotent: re-running the same day's
    signal overwrites rather than duplicating.
    """
    batch = signal_batch or f"{strategy_id}-{trade_date}"
    generated = datetime.now(CN_TZ).isoformat(timespec="seconds")
    rows: list[dict[str, Any]] = []
    for item in to_conditional_orders(
        orders, strategy_id=strategy_id, trade_date=trade_date, price_offset_bps=price_offset_bps
    ):
        rows.append(
            {
                **item,
                "portfolio_value": float(portfolio_value),
                "signal_batch": batch,
                "generated_at": generated,
                "status": "pending",
            }
        )
    return rows


# ── stage 4: execution reconciliation ───────────────────────────────────

@dataclass
class DeviationReport:
    """Intended orders versus actual fills."""

    trade_date: str
    strategy_id: str
    matched: int = 0
    missing: list[dict[str, Any]] = field(default_factory=list)
    unexpected: list[dict[str, Any]] = field(default_factory=list)
    quantity_breaks: list[dict[str, Any]] = field(default_factory=list)
    price_slippage: list[dict[str, Any]] = field(default_factory=list)
    filled_notional: float = 0.0
    intended_notional: float = 0.0

    @property
    def fill_ratio(self) -> float:
        if self.intended_notional <= 0:
            return float("nan")
        return self.filled_notional / self.intended_notional

    @property
    def is_clean(self) -> bool:
        return not (self.missing or self.unexpected or self.quantity_breaks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "strategy_id": self.strategy_id,
            "matched": self.matched,
            "n_missing": len(self.missing),
            "n_unexpected": len(self.unexpected),
            "n_quantity_breaks": len(self.quantity_breaks),
            "n_price_slippage": len(self.price_slippage),
            "intended_notional": self.intended_notional,
            "filled_notional": self.filled_notional,
            "fill_ratio": self.fill_ratio,
            "is_clean": self.is_clean,
            "missing": self.missing,
            "unexpected": self.unexpected,
            "quantity_breaks": self.quantity_breaks,
            "price_slippage": self.price_slippage,
        }

    def render_markdown(self) -> str:
        lines = [
            f"# 执行对账 · {self.strategy_id} · {self.trade_date}",
            "",
            f"- 意图订单名义金额：{self.intended_notional:,.0f}",
            f"- 实际成交名义金额：{self.filled_notional:,.0f}",
            f"- 成交比例：{self.fill_ratio:.4f}" if math.isfinite(self.fill_ratio) else "- 成交比例：n/a",
            f"- 结论：{'✅ 无偏差' if self.is_clean else '⚠️ 存在偏差'}",
            "",
            f"- 未成交：{len(self.missing)}　计划外成交：{len(self.unexpected)}　"
            f"数量不符：{len(self.quantity_breaks)}　价格滑点：{len(self.price_slippage)}",
        ]
        for label, rows, keys in (
            ("未成交", self.missing, ("code", "side", "shares")),
            ("计划外成交", self.unexpected, ("code", "side", "shares")),
            ("数量不符", self.quantity_breaks, ("code", "intended", "filled", "delta")),
            ("价格滑点", self.price_slippage, ("code", "side", "reference", "average", "slippage_bps")),
        ):
            if not rows:
                continue
            lines.extend(["", f"## {label}", "", "| " + " | ".join(keys) + " |",
                          "|" + "---|" * len(keys)])
            for row in rows[:50]:
                lines.append("| " + " | ".join(str(row.get(key, "")) for key in keys) + " |")
        return "\n".join(lines) + "\n"


def reconcile_execution(
    orders: Sequence[Order],
    fills: pd.DataFrame,
    *,
    trade_date: str,
    strategy_id: str,
    quantity_tolerance: float = 0.0,
    slippage_warn_bps: float = 20.0,
    code_col: str = "code",
    shares_col: str = "shares",
    price_col: str = "price",
    side_col: str = "side",
) -> DeviationReport:
    """Compare intended orders with actual fills.

    ``quantity_tolerance`` is a *fraction* of the intended quantity: 0.0 means
    every share must match. Partial fills are reported as quantity breaks rather
    than silently accepted, because a half-filled basket is a different portfolio
    from the one that was validated.
    """
    required = {code_col, shares_col, price_col}
    missing_columns = sorted(required - set(fills.columns))
    if missing_columns:
        raise SignalError(f"fills are missing columns: {', '.join(missing_columns)}")

    report = DeviationReport(trade_date=trade_date, strategy_id=strategy_id)
    report.intended_notional = float(sum(order.notional for order in orders))

    actual: dict[str, dict[str, Any]] = {}
    for _, row in fills.iterrows():
        code = str(row[code_col])
        entry = actual.setdefault(code, {"shares": 0, "notional": 0.0, "side": None})
        shares = int(row[shares_col])
        entry["shares"] += shares
        entry["notional"] += shares * float(row[price_col])
        entry["side"] = str(row[side_col]) if side_col in fills.columns else None
        report.filled_notional += shares * float(row[price_col])

    for order in orders:
        entry = actual.get(order.code)
        if entry is None or entry["shares"] == 0:
            report.missing.append(
                {"code": order.code, "side": order.side, "shares": order.shares,
                 "reason": order.reason}
            )
            continue

        deviation = abs(entry["shares"] - order.shares) / max(order.shares, 1)
        if deviation > quantity_tolerance:
            report.quantity_breaks.append(
                {
                    "code": order.code,
                    "side": order.side,
                    "intended": order.shares,
                    "filled": entry["shares"],
                    "delta": entry["shares"] - order.shares,
                    "deviation": round(deviation, 6),
                }
            )
        else:
            report.matched += 1

        average = entry["notional"] / entry["shares"]
        # Implementation shortfall, signed so that POSITIVE always means worse:
        # a buy filled above the reference and a sell filled below it both come
        # out positive. Readers should never have to reason about the direction
        # of the trade to interpret the sign.
        direction = 1.0 if order.side == "buy" else -1.0
        slippage = direction * (average - order.reference_price) / order.reference_price * 10_000.0
        if abs(slippage) > slippage_warn_bps:
            report.price_slippage.append(
                {
                    "code": order.code,
                    "side": order.side,
                    "reference": round(order.reference_price, 4),
                    "average": round(average, 4),
                    "slippage_bps": round(slippage, 2),
                }
            )

    intended_codes = {order.code for order in orders}
    for code, entry in sorted(actual.items()):
        if code not in intended_codes and entry["shares"] != 0:
            report.unexpected.append(
                {"code": code, "side": entry["side"], "shares": entry["shares"]}
            )

    report.price_slippage.sort(key=lambda row: -abs(row["slippage_bps"]))
    return report
