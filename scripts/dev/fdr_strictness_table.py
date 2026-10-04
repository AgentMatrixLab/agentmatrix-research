"""How strict is BH-FDR at q = 0.05 over a batch of N factors?

The frozen `rank_ic` gate screens each factor at |t| >= 1.65 in isolation. Adding
batch-level FDR control raises the bar, because the k-th smallest p-value must
clear k/N * q. This prints the |t| a factor needs for each rank, so the delivery
target can be planned against the real requirement rather than the gate alone.

Read-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scipy import stats  # noqa: E402

DOF = 419  # ~420 OOS trading days minus one
Q = 0.05
BATCHES = [300, 500, 900, 1058]


def t_for_p(p: float, dof: int = DOF) -> float:
    return float(stats.t.isf(p / 2.0, dof))


def main() -> int:
    print(f"BH-FDR at q={Q}, degrees of freedom={DOF} (two-sided)")
    print()
    print("a factor must be at least this extreme to be the k-th discovery:")
    print()
    header = f"{'rank k':>7} | " + " | ".join(f"N={n:<4}" for n in BATCHES)
    print(header)
    print("-" * len(header))
    for k in (1, 10, 25, 50, 100, 200, 300, 400):
        row = []
        for n in BATCHES:
            threshold = k / n * Q
            if threshold >= 1.0:
                row.append(f"{'n/a':<6}")
            else:
                row.append(f"|t|>={t_for_p(threshold):.2f}")
        print(f"{k:>7} | " + " | ".join(f"{cell:<6}" for cell in row))

    print()
    print("the same figure for the frozen gate in isolation:")
    print(f"  |t| >= 1.65  (one-sided 5%, equivalently two-sided p = {2 * stats.t.sf(1.65, DOF):.4f})")
    print()
    print("reading the table: to deliver 300 factors from a batch of 900, the")
    print("300th smallest p-value must clear 300/900 * 0.05 = 0.0167, i.e. |t| ~ 2.4.")
    print("That is substantially stricter than the gate's 1.65, and it is a")
    print("property of multiple-testing control, not of any threshold we chose.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
