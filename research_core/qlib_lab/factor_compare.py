"""Multi-factor comparison and redundancy detection.

Computes pairwise correlations, IC decay curves, and cluster analysis
for registered factors.  Uses Qlib data for factor value computation.

Core functions:
  - pairwise_correlation(): N×N correlation matrix
  - find_redundant(): flags factors with correlation > threshold
  - ic_decay_curve(): IC at multiple horizons
  - factor_cluster(): correlation-based clustering
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _get_lab():
    from research_core.qlib_lab.factor_miner import QlibFactorLab
    from research_core.qlib_lab.runtime import QlibWorkspaceConfig
    config = QlibWorkspaceConfig(provider_uri="data/qlib/cn_data", region="cn")
    return QlibFactorLab(config=config)


def _load_factor_values(
    factor_ids: list[str],
    start: str = "2010-01-01",
    end: str = "2019-12-31",
) -> pd.DataFrame:
    """Load factor values for multiple factors, aligned by date+instrument.

    Returns DataFrame with MultiIndex (datetime, instrument) and one column per factor.
    """
    lab = _get_lab()
    from registry.factor_registry import get_factor_definition

    frames = {}
    for fid in factor_ids:
        try:
            info = get_factor_definition(fid)
            if info is None:
                continue
            df = lab.fetch_expression_frame(
                info["expression"], start_time=start, end_time=end,
            )
            if df is not None and len(df) > 0:
                frames[fid] = df["factor"]
        except Exception:
            continue

    if not frames:
        raise ValueError("No factor data loaded")

    result = pd.DataFrame(frames)
    result = result.dropna()
    return result


def pairwise_correlation(
    factor_ids: list[str],
    start: str = "2010-01-01",
    end: str = "2019-12-31",
) -> pd.DataFrame:
    """Compute N×N correlation matrix for factor values.

    Args:
        factor_ids: list of factor IDs from the registry
        start, end: date range

    Returns:
        Correlation matrix (DataFrame, indexed by factor_id)
    """
    values = _load_factor_values(factor_ids, start, end)
    return values.corr()


def find_redundant(
    new_factor_id: str,
    existing_ids: list[str],
    threshold: float = 0.7,
    start: str = "2010-01-01",
    end: str = "2019-12-31",
) -> dict:
    """Check if a new factor is redundant with existing ones.

    Args:
        new_factor_id: the factor to check
        existing_ids: list of existing factor IDs to compare against
        threshold: correlation threshold for redundancy (default 0.7)
        start, end: date range

    Returns:
        dict with keys: redundant (bool), highest_corr (float),
        highest_with (str), all_correlations (dict)
    """
    all_ids = [new_factor_id] + list(existing_ids)
    corr_matrix = pairwise_correlation(all_ids, start, end)

    if new_factor_id not in corr_matrix.index:
        return {"redundant": False, "error": "new factor not loadable"}

    correlations = {}
    max_corr = 0.0
    max_with = ""

    for eid in existing_ids:
        if eid not in corr_matrix.index:
            continue
        c = corr_matrix.loc[new_factor_id, eid]
        if pd.notna(c):
            correlations[eid] = round(float(c), 4)
            if abs(c) > abs(max_corr):
                max_corr = abs(c)
                max_with = eid

    return {
        "redundant": abs(max_corr) > threshold,
        "highest_corr": round(max_corr, 4),
        "highest_with": max_with,
        "threshold": threshold,
        "all_correlations": correlations,
    }


def ic_decay_curve(
    factor_ids: list[str],
    horizons: list[int] | None = None,
    start: str = "2010-01-01",
    end: str = "2019-12-31",
) -> pd.DataFrame:
    """Compute IC decay curves: IC at multiple horizons for each factor.

    Args:
        factor_ids: list of factor IDs
        horizons: list of forward horizons in days (default [1, 5, 10, 20, 60])
        start, end: date range

    Returns:
        DataFrame with rows=factor_id, columns=horizon_1d/horizon_5d/...
    """
    if horizons is None:
        horizons = [1, 5, 10, 20, 60]

    lab = _get_lab()
    from registry.factor_registry import get_factor_definition

    results = {}
    for fid in factor_ids:
        info = get_factor_definition(fid)
        if info is None:
            continue

        expression = info.get("expression", "")
        if not expression:
            continue

        row = {}
        for h in horizons:
            try:
                r = lab.mine_expression(
                    name=fid, expression=expression, description="ic_decay",
                    start_time=start, end_time=end, horizon=h,
                    source="compare", author="system",
                )
                row[f"horizon_{h}d"] = round(r["top_metrics"]["ic_mean"], 6)
            except Exception:
                row[f"horizon_{h}d"] = None
        results[fid] = row

    return pd.DataFrame.from_dict(results, orient="index")


def factor_cluster(
    factor_ids: list[str],
    n_clusters: int = 5,
    start: str = "2010-01-01",
    end: str = "2019-12-31",
) -> dict:
    """Cluster factors by value correlation.

    Args:
        factor_ids: list of factor IDs
        n_clusters: number of clusters
        start, end: date range

    Returns:
        dict with keys: clusters (list of list of factor_ids),
        cluster_labels (dict factor_id → cluster_id)
    """
    corr_matrix = pairwise_correlation(factor_ids, start, end)

    # Convert correlation to distance: 1 - |corr|
    distance = 1 - corr_matrix.abs()

    from sklearn.cluster import AgglomerativeClustering
    try:
        clustering = AgglomerativeClustering(
            n_clusters=min(n_clusters, len(factor_ids)),
            metric="precomputed", linkage="average",
        )
        labels = clustering.fit_predict(distance.values)
    except Exception:
        # Fallback: simple threshold-based grouping
        labels = np.zeros(len(factor_ids), dtype=int)
        cluster_id = 0
        assigned = set()
        for i, fi in enumerate(corr_matrix.index):
            if i in assigned:
                continue
            assigned.add(i)
            labels[i] = cluster_id
            for j, fj in enumerate(corr_matrix.index):
                if j in assigned:
                    continue
                if abs(corr_matrix.iloc[i, j]) > 0.5:
                    assigned.add(j)
                    labels[j] = cluster_id
            cluster_id += 1

    clusters = {}
    for i, fid in enumerate(corr_matrix.index):
        cid = int(labels[i])
        clusters.setdefault(f"cluster_{cid}", []).append(fid)

    return {
        "n_clusters": len(clusters),
        "clusters": {k: sorted(v) for k, v in clusters.items()},
        "label_map": {fid: int(labels[i]) for i, fid in enumerate(corr_matrix.index)},
    }
