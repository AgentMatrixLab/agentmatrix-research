"""Readers for the frozen validator's `validation_result.json`.

The frozen validator writes rank-IC statistics under date-horizon keys such as
``"5d"``, ``"10d"`` and ``"20d"`` (see ``deterministic_validation._ic_summary``
call sites and ``batch_validation``). Anything downstream that guesses a
different key shape silently finds nothing.

That failure mode is nasty precisely because it is quiet: an FDR pass over a
batch whose statistics were never read reports "0 of 900 factors passed", which
looks exactly like a strict-but-working correction. This module is the single
place that knows the key shape, so every consumer fails the same, loud way.

Kept separate from `robustness` (the mathematics) and `supplementary` (the batch
report) so both can share it without either depending on the other.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

__all__ = [
    "ValidationResultError",
    "horizon_keys",
    "resolve_primary_horizon",
    "resolve_rank_ic_entry",
    "extract_rank_ic_statistic",
]


class ValidationResultError(ValueError):
    """Raised when a validation result cannot yield the requested statistic."""


def horizon_keys(horizon: int) -> tuple[str, ...]:
    """Every key shape a horizon has appeared under, most specific first.

    ``"10d"`` is what the frozen validator actually writes; the bare forms are
    accepted so hand-written fixtures and older artefacts keep working.
    """
    return (f"{horizon}d", f"{horizon}D", str(horizon), str(float(horizon)))


def _as_horizon(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return int(value)
    if isinstance(value, str):
        text = value.strip().rstrip("dD")
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def resolve_primary_horizon(result: Mapping[str, Any], default: int = 10) -> int:
    """The horizon to read, honouring an explicit declaration when present."""
    explicit = _as_horizon(result.get("primary_horizon"))
    if explicit is not None:
        return explicit

    table = result.get("rank_ic")
    if isinstance(table, Mapping):
        candidates = sorted(
            horizon
            for horizon in (_as_horizon(key) for key in table)
            if horizon is not None
        )
        if default in candidates:
            return default
        if len(candidates) == 1:
            return candidates[0]
    return default


def resolve_rank_ic_entry(
    result: Mapping[str, Any], horizon: int
) -> Mapping[str, Any] | None:
    """Return the rank-IC entry for ``horizon``, or None when absent.

    Only a table that exists but has no matching key raises: that means the
    caller asked for a horizon the result genuinely does not carry, which is a
    bug worth surfacing. An absent table is a different condition and returns
    None so callers can classify rather than crash.
    """
    table = result.get("rank_ic")
    if not isinstance(table, Mapping) or not table:
        return None

    for key in horizon_keys(horizon):
        entry = table.get(key)
        if isinstance(entry, Mapping):
            return entry

    # Nothing matched. If the table has exactly one horizon, use it rather than
    # failing, because the caller's number is then unambiguous.
    usable = [entry for entry in table.values() if isinstance(entry, Mapping)]
    if len(usable) == 1:
        return usable[0]

    raise ValidationResultError(
        f"{result.get('factor_id', '<unknown>')}: rank_ic has no entry for horizon "
        f"{horizon} (keys present: {sorted(map(str, table.keys()))})"
    )


def extract_rank_ic_statistic(
    result: Mapping[str, Any], horizon: int
) -> tuple[float, int]:
    """Pull ``(t_stat, days)`` for a horizon, coercing every failure mode.

    Returns NaN/0 rather than raising when the entry exists but simply does not
    carry a usable statistic: an untestable factor is a legitimate outcome, not
    an error. Structural problems still raise.
    """
    entry = resolve_rank_ic_entry(result, horizon)
    if entry is None:
        raise ValidationResultError(
            f"{result.get('factor_id', '<unknown>')}: validation result carries no rank_ic table"
        )

    raw_t = entry.get("t_stat", float("nan"))
    try:
        t_stat = float(raw_t)
    except (TypeError, ValueError):
        t_stat = float("nan")

    raw_days = entry.get("days", 0)
    try:
        days = int(raw_days)
    except (TypeError, ValueError):
        days = 0
    return t_stat, max(days, 0)
