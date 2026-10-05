"""Benchmark `cluster_factors` at delivery scale.

`cluster_factors` is a hand-written agglomerative average-linkage loop: it rescans every active
pair on every pass and recomputes each pair's block mean with `np.ix_` + `.mean()`, with no
Lance-Williams update. That is O(n^3) in Python-level calls, and the delivery clusters ~300-600
factors -- far more than any rehearsal ever passed it. This measures whether that is minutes or
hours, because finding out at the end of a 20-hour run would be too late.

    python -X utf8 scripts/dev/benchmark_clustering.py --sizes 300 450 600
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research_core.factor_lab.scoring import cluster_factors  # noqa: E402


def synthetic_correlation(n: int, *, blocks: int = 20, seed: int = 7) -> pd.DataFrame:
    """A correlation matrix with realistic block structure.

    Factors from one family really are near-duplicates (the delivered set has whole families of
    ALPHA360:HIGH* differing only by window), so the matrix is built from blocks with high
    intra-block correlation. That makes the merge loop do close to its worst-case work, which
    is the case worth timing.
    """
    rng = np.random.default_rng(seed)
    size = max(1, n // blocks)
    matrix = np.eye(n)
    labels = [f"F{index:04d}" for index in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            same = i // size == j // size
            value = 0.85 + rng.normal(0, 0.05) if same else rng.normal(0, 0.25)
            value = float(np.clip(value, -0.99, 0.99))
            matrix[i, j] = matrix[j, i] = value
    np.fill_diagonal(matrix, 1.0)
    return pd.DataFrame(matrix, index=labels, columns=labels)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sizes", type=int, nargs="+", default=[300, 450, 600])
    parser.add_argument("--threshold", type=float, default=0.7)
    args = parser.parse_args(argv)

    print(f"{'n':>6} {'seconds':>10} {'clusters':>9} {'biggest':>8}  projected")
    for n in args.sizes:
        matrix = synthetic_correlation(n)
        started = time.perf_counter()
        result = cluster_factors(matrix, threshold=args.threshold)
        elapsed = time.perf_counter() - started
        sizes = [cluster["size"] for cluster in result["clusters"]]
        projected = ""
        if elapsed > 5:
            projected = f"{elapsed / 60:.1f} min"
        print(
            f"{n:>6} {elapsed:>10.2f} {result['n_clusters']:>9} {max(sizes):>8}  {projected}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
