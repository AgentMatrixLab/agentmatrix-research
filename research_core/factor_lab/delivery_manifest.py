"""Fuse every evidence layer into the delivery manifest the client receives.

The pieces each produce their own artifact: `factor_catalog.csv` carries candidate
metadata and the frozen-gate verdict, `supplementary_report.json` carries FDR and
industry-neutral retention, `scoring.py` carries the composite score and tier, and
the clustering carries the cluster a factor belongs to. None of them is the
delivery on its own, and handing the client four files and a paragraph of
instructions is how the numbers end up being read out of context.

This module joins them on ``factor_id`` into one row per factor with a frozen
column set, and derives the one field the delivery actually turns on:
``in_delivery_package``.

Two rules are structural, not advisory:

* **A factor enters the package only if it cleared every frozen gate AND counts
  as alpha.** A risk exposure runs and reports its status, but the ruling is that
  it never enters the package, so it is excluded here rather than filtered by a
  reader who might miss it.
* **A tier is only ever assigned to a factor that passed.** The scorer refuses
  rejected factors, so a missing tier and a rejected status travel together; this
  module never fills a tier in from anything else.

Read-only: builds and writes rows, touches no other artifact.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "DELIVERY_MANIFEST_COLUMNS",
    "PACKAGE_TIERS",
    "DeliveryManifestError",
    "build_delivery_manifest",
    "summarise_manifest",
    "write_delivery_manifest",
]

#: Column order is part of the contract: downstream spreadsheets and the client's
#: own tooling key off it, so appending is fine but reordering is a breaking change.
DELIVERY_MANIFEST_COLUMNS: tuple[str, ...] = (
    # identity and provenance
    "factor_id",
    "name",
    "formula",
    "category",
    "required_fields",
    "direction",
    "window",
    # frozen-gate verdict, taken verbatim from the validator
    "status",
    "failed_gates",
    "reason",
    "result_hash",
    "evidence",
    # alpha accounting
    "risk_exposure",
    "counts_as_alpha",
    # additive robustness layer
    "p_value",
    "p_adjusted",
    "fdr_accepted",
    "industry_neutral_retention",
    # scoring and redundancy
    "tier",
    "composite",
    "cluster_id",
    "cluster_role",
    "cluster_size",
    "cluster_mean_corr",
    # the delivery decision
    "in_delivery_package",
)

#: The tiers the scoring card marks as rollout-priority. NOT an inclusion rule: the delivery
#: package is decided by the eight frozen gates (see `build_delivery_manifest`). Reported
#: separately by `summarise_manifest` so the priority split is still visible.
PACKAGE_TIERS = ("S", "A")


class DeliveryManifestError(ValueError):
    """Raised when the inputs cannot be fused into a coherent manifest."""


def _empty_row(factor_id: str) -> dict[str, str]:
    return {column: "" for column in DELIVERY_MANIFEST_COLUMNS} | {"factor_id": factor_id}


def _format(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        return f"{value:.6f}"
    return str(value)


def build_delivery_manifest(
    catalog_rows: Iterable[Mapping[str, Any]],
    *,
    scoring: Mapping[str, Any] | None = None,
    supplementary: Mapping[str, Any] | None = None,
    clusters: Sequence[Mapping[str, Any]] | None = None,
    representatives: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Join the layered evidence into one row per factor.

    Every input is optional so the manifest can be produced at any point in the
    pipeline; the columns simply stay empty for layers that have not run, which is
    how a partly-complete delivery is represented honestly instead of by guessing.
    """
    rows = list(catalog_rows)
    if not rows:
        raise DeliveryManifestError("no catalog rows were supplied")

    seen: set[str] = set()
    for row in rows:
        factor_id = str(row.get("factor_id", "")).strip()
        if not factor_id:
            raise DeliveryManifestError("a catalog row has an empty factor_id")
        if factor_id in seen:
            raise DeliveryManifestError(f"catalog has a duplicate factor_id: {factor_id}")
        seen.add(factor_id)

    scores = {
        str(item["factor_id"]): item
        for item in (scoring or {}).get("factors", [])
        if item.get("factor_id")
    }
    supplementary_by_id = {
        str(item["factor_id"]): item
        for item in (supplementary or {}).get("factors", [])
        if item.get("factor_id")
    }

    cluster_of: dict[str, Mapping[str, Any]] = {}
    for cluster in clusters or []:
        for member in cluster.get("members", []):
            cluster_of[str(member)] = cluster
    role_of = {
        str(item.get("representative")): "representative" for item in representatives or []
    }

    manifest: list[dict[str, str]] = []
    for row in rows:
        factor_id = str(row["factor_id"])
        entry = _empty_row(factor_id)

        for column in ("name", "formula", "category", "required_fields", "direction", "window",
                       "status", "failed_gates", "reason", "result_hash", "evidence",
                       "risk_exposure", "counts_as_alpha"):
            entry[column] = _format(row.get(column))

        score = scores.get(factor_id)
        if score is not None:
            entry["tier"] = _format(score.get("tier"))
            entry["composite"] = _format(score.get("composite"))

        extra = supplementary_by_id.get(factor_id)
        if extra is not None:
            entry["p_value"] = _format(extra.get("p_value"))
            entry["p_adjusted"] = _format(extra.get("p_adjusted"))
            entry["fdr_accepted"] = _format(extra.get("fdr_accepted"))
            neutral = extra.get("industry_neutral_ic")
            if isinstance(neutral, Mapping):
                entry["industry_neutral_retention"] = _format(neutral.get("retention"))

        cluster = cluster_of.get(factor_id)
        if cluster is not None:
            entry["cluster_id"] = _format(cluster.get("cluster_id"))
            entry["cluster_role"] = role_of.get(factor_id, "member")
            entry["cluster_size"] = _format(cluster.get("size"))
            entry["cluster_mean_corr"] = _format(cluster.get("mean_intra_correlation"))

        passed = entry["status"] == "validated"
        is_alpha = entry["counts_as_alpha"] in ("", "true")
        # The delivery package is defined by the EIGHT FROZEN GATES, not by the scoring card.
        #
        # Placing `tier in PACKAGE_TIERS` here made the card a *threshold*: the headline count
        # silently became "gate-passers that also cleared composite >= 55" instead of
        # "gate-passers". The 300 target is computed the second way -- the agreed feasibility
        # arithmetic is the candidate count times the measured gate pass rate -- and the card
        # itself is still a draft (open question Q4), so letting it decide inclusion would
        # report a delivery far below the contracted number with no validation reason.
        #
        # The tier is still written on every row, and `summarise_manifest` still reports the
        # narrower S/A count, so the client can sequence the rollout by score. It is a
        # ranking, not a gate: nothing here can admit a factor the frozen validator rejected.
        entry["in_delivery_package"] = _format(bool(passed and is_alpha))
        manifest.append(entry)

    return manifest


def summarise_manifest(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Counts a reader would otherwise have to derive by hand."""
    def count(predicate) -> int:  # noqa: ANN001
        return sum(1 for row in rows if predicate(row))

    tiers = {tier: count(lambda r, t=tier: r.get("tier") == t) for tier in ("S", "A", "B", "C")}
    delivered = [row for row in rows if str(row.get("in_delivery_package")) == "true"]
    clusters = {str(row.get("cluster_id")) for row in delivered if row.get("cluster_id")}

    return {
        "total": len(rows),
        "validated": count(lambda r: r.get("status") == "validated"),
        "rejected": count(lambda r: r.get("status") == "rejected"),
        "not_run": count(lambda r: r.get("status") == "not_run"),
        "risk_exposure": count(lambda r: str(r.get("risk_exposure")) == "true"),
        "tier_counts": tiers,
        "fdr_accepted": count(lambda r: str(r.get("fdr_accepted")) == "true"),
        "in_delivery_package": len(delivered),
        # The same set narrowed to rollout-priority tiers. Reported so the reader can see how
        # much of the package the scoring card rates S/A without that deciding the headline.
        "in_delivery_package_tier_sa": count(
            lambda r: str(r.get("in_delivery_package")) == "true"
            and r.get("tier") in PACKAGE_TIERS
        ),
        "delivered_clusters": len(clusters),
        "representatives": count(
            lambda r: str(r.get("in_delivery_package")) == "true"
            and r.get("cluster_role") == "representative"
        ),
    }


def write_delivery_manifest(rows: Sequence[Mapping[str, str]], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(DELIVERY_MANIFEST_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in DELIVERY_MANIFEST_COLUMNS})
    return target
