from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def summarize_legacy_accounting(
    transactions: Iterable[Mapping[str, Any]],
    nav_values: Iterable[float],
) -> dict[str, float | int | str]:
    """Build the canonical accounting summary for the Chenxi compatibility bridge.

    Turnover follows the same two-sided convention as the other AgentMatrix
    parsers: absolute traded notional divided by twice average portfolio equity.
    The calculation uses the complete engine transaction ledger, not the
    display-only trade list which may be truncated.
    """

    rows = list(transactions)
    notionals = []
    for row in rows:
        amount = float(row.get("amount", 0.0) or 0.0)
        if not amount:
            amount = float(row.get("shares", 0.0) or 0.0) * float(
                row.get("price", 0.0) or 0.0
            )
        notionals.append(abs(amount))

    equity = [float(value) for value in nav_values if float(value) > 0]
    average_equity = sum(equity) / len(equity) if equity else 0.0
    traded_notional = sum(notionals)
    turnover = traded_notional / max(average_equity * 2.0, 1.0)
    return {
        "turnover": float(turnover),
        "traded_notional": float(traded_notional),
        "average_equity": float(average_equity),
        "transaction_count": len(rows),
        "turnover_convention": "two_sided_notional_over_twice_average_equity",
    }
