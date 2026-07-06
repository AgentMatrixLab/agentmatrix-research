"""
Factor Similarity Detection — Prevent duplicate factor mining.

Checks a new factor against the existing factor registry to detect
near-duplicates (high Pearson/Spearman correlation in cross-section).

When a new candidate factor is proposed, this module:
1. Loads all previously computed factor panels from the runtime store
2. Computes pairwise cross-sectional correlation
3. Flags factors with absolute correlation > threshold
4. Returns a similarity report suitable for:
   - Rejecting duplicate PRs
   - Warning researchers before they invest time
   - Building a factor correlation matrix

Usage:
    from research_core.factor_lab.similarity import (
        check_duplicate,
        build_similarity_matrix,
        find_similar_factors,
    )

    # Quick check: is my factor already in the registry?
    report = check_duplicate(
        candidate_frame=my_factor_frame,
        candidate_name="my_new_momentum",
        existing_frames=load_all_factor_frames(),
        threshold=0.7,
    )

    if report["has_duplicate"]:
        print(f"⚠️  Your factor looks like {report['top_match']} (ρ={report['top_correlation']:.3f})")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from research_core.factor_lab.runtime import FactorLabWorkspaceConfig, now_iso


def _cross_sectional_correlation(
    frame_a: pd.DataFrame,
    frame_b: pd.DataFrame,
    factor_a: str,
    factor_b: str,
    *,
    date_col: str = "date",
    code_col: str = "code",
    method: str = "spearman",
) -> tuple[float, float, int]:
    """Compute mean cross-sectional correlation between two factor panels.

    For each date, compute correlation between the two factor value vectors,
    then average across dates.

    Args:
        frame_a, frame_b: DataFrames with [date, code, factor_value]
        factor_a, factor_b: Column names containing factor values
        method: "spearman" (default, more robust) or "pearson"

    Returns:
        (mean_correlation, std_correlation, n_dates)
    """
    merged = pd.merge(
        frame_a[[date_col, code_col, factor_a]],
        frame_b[[date_col, code_col, factor_b]],
        on=[date_col, code_col],
        how="inner",
    )

    if merged.empty:
        return float("nan"), float("nan"), 0

    cors = []
    for _, group in merged.groupby(date_col):
        vals_a = group[factor_a].dropna()
        vals_b = group[factor_b].dropna()

        # Must align on same codes
        common = vals_a.index.intersection(vals_b.index)
        if len(common) < 10:
            continue

        a = vals_a.loc[common]
        b = vals_b.loc[common]

        if method == "spearman":
            corr = a.rank().corr(b.rank())
        else:
            corr = a.corr(b)

        if pd.notna(corr):
            cors.append(corr)

    if not cors:
        return float("nan"), float("nan"), 0

    return float(np.mean(cors)), float(np.std(cors)), len(cors)


def find_similar_factors(
    candidate_frame: pd.DataFrame,
    candidate_name: str,
    existing_frames: dict[str, pd.DataFrame],
    *,
    threshold: float = 0.7,
    method: str = "spearman",
    top_k: int = 5,
) -> dict[str, Any]:
    """Find existing factors similar to a candidate.

    Args:
        candidate_frame: DataFrame with [date, code, candidate_name]
        candidate_name: Name of the candidate factor column
        existing_frames: Dict of {factor_name: DataFrame} for all existing factors.
            Each DataFrame must have [date, code, <factor_name>].
        threshold: Correlation above this absolute value is flagged as duplicate
        method: "spearman" or "pearson"
        top_k: Number of top matches to return

    Returns:
        Report dict with:
        - has_duplicate: bool
        - top_match: str (closest factor name)
        - top_correlation: float
        - matches: list of all matches sorted by |correlation|
    """
    matches = []

    for existing_name, existing_frame in existing_frames.items():
        if existing_name == candidate_name:
            continue

        # Find the factor column in the existing frame
        factor_cols = [
            c for c in existing_frame.columns
            if c not in ("date", "code") and c == existing_name
        ]
        if not factor_cols:
            continue

        mean_corr, std_corr, n_dates = _cross_sectional_correlation(
            candidate_frame,
            existing_frame,
            candidate_name,
            existing_name,
            method=method,
        )

        if pd.notna(mean_corr):
            matches.append({
                "factor_name": existing_name,
                "mean_correlation": round(mean_corr, 6),
                "std_correlation": round(std_corr, 6),
                "abs_correlation": round(abs(mean_corr), 6),
                "n_dates": n_dates,
            })

    # Sort by absolute correlation descending
    matches.sort(key=lambda x: x["abs_correlation"], reverse=True)

    top_matches = matches[:top_k]
    above_threshold = [m for m in matches if m["abs_correlation"] >= threshold]

    return {
        "candidate_name": candidate_name,
        "threshold": threshold,
        "method": method,
        "has_duplicate": len(above_threshold) > 0,
        "duplicate_count": len(above_threshold),
        "top_match": top_matches[0]["factor_name"] if top_matches else None,
        "top_correlation": top_matches[0]["abs_correlation"] if top_matches else None,
        "above_threshold": above_threshold[:top_k],
        "top_matches": top_matches,
        "total_compared": len(matches),
    }


def check_duplicate(
    candidate_frame: pd.DataFrame,
    candidate_name: str,
    existing_frames: dict[str, pd.DataFrame],
    *,
    threshold: float = 0.7,
) -> dict[str, Any]:
    """Convenience wrapper: check if a candidate factor duplicates an existing one.

    Returns the same report as find_similar_factors, but raises no error.
    Callers should check report["has_duplicate"].
    """
    return find_similar_factors(
        candidate_frame,
        candidate_name,
        existing_frames,
        threshold=threshold,
    )


def build_similarity_matrix(
    factor_frames: dict[str, pd.DataFrame],
    *,
    method: str = "spearman",
) -> pd.DataFrame:
    """Build a full pairwise similarity matrix for all factors.

    Args:
        factor_frames: {factor_name: DataFrame with [date, code, factor_name]}
        method: "spearman" or "pearson"

    Returns:
        DataFrame: N×N correlation matrix (factor_name × factor_name)
    """
    names = sorted(factor_frames.keys())
    n = len(names)
    matrix = pd.DataFrame(np.eye(n), index=names, columns=names)

    for i, name_a in enumerate(names):
        for j, name_b in enumerate(names):
            if i >= j:
                continue
            mean_corr, _, _ = _cross_sectional_correlation(
                factor_frames[name_a],
                factor_frames[name_b],
                name_a,
                name_b,
                method=method,
            )
            if pd.notna(mean_corr):
                matrix.loc[name_a, name_b] = mean_corr
                matrix.loc[name_b, name_a] = mean_corr

    return matrix


def load_factor_frames_from_runtime(
    config: FactorLabWorkspaceConfig | None = None,
    library: str = "alpha101",
) -> dict[str, pd.DataFrame]:
    """Load all computed factor frames from the runtime store.

    This is a helper that scans runtime/factor_lab/frames/ for CSV exports
    and loads them into DataFrames.

    Args:
        config: FactorLab workspace config (defaults to default paths)
        library: Library name (e.g. "alpha101", "gtja191")

    Returns:
        {factor_name: DataFrame}
    """
    if config is None:
        config = FactorLabWorkspaceConfig()
    config.ensure_directories()

    frames_dir = config.runtime_root / "frames"
    if not frames_dir.exists():
        return {}

    result = {}
    for csv_path in sorted(frames_dir.glob(f"*{library}*_factor_frame.csv")):
        try:
            df = pd.read_csv(csv_path)
            df["date"] = pd.to_datetime(df["date"])
            # Assume factor columns are everything except date, code
            factor_cols = [c for c in df.columns if c not in ("date", "code")]
            for col in factor_cols:
                result[col] = df[["date", "code", col]].copy()
        except Exception:
            continue

    return result


def export_similarity_report(
    report: dict[str, Any],
    config: FactorLabWorkspaceConfig | None = None,
) -> str:
    """Export a similarity report JSON to the runtime store.

    Returns:
        Path string to the written report.
    """
    if config is None:
        config = FactorLabWorkspaceConfig()
    config.ensure_directories()

    candidate = report["candidate_name"]
    path = config.runtime_root / "similarity" / f"{candidate}_similarity_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {**report, "generated_at": now_iso()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
