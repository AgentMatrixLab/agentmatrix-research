from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from research_core.factor_lab import FactorLabWorkspaceConfig, get_factor_lab_job


ARTIFACT_LABELS: dict[str, tuple[str, str]] = {
    "proof": ("proof.json", "single_factor_proof"),
    "truth_compare": ("truth_compare.json", "truth_comparison"),
    "evaluation_json": ("evaluation.json", "job_evaluation"),
    "evaluation_markdown": ("evaluation.md", "job_evaluation_markdown"),
    "research_report_json": ("proof_report.json", "research_report_json"),
    "research_report_markdown": ("proof_report.md", "research_report_markdown"),
    "factor_frame": ("factor_frame.csv", "factor_value_frame"),
    "catalog": ("catalog.json", "factor_catalog"),
    "specs": ("specs.json", "factor_specs"),
}


def artifact_url(job_id: str, kind: str, *, factor_name: str | None = None) -> str:
    base = f"/api/agents/factor-lab/artifacts/{quote(job_id, safe='')}/{quote(kind, safe='')}"
    if factor_name and kind in {"proof", "truth_compare"}:
        return f"{base}?factor={quote(factor_name, safe='')}"
    return base


def list_job_artifacts(
    job_id: str,
    *,
    factor_name: str | None = None,
    workspace: FactorLabWorkspaceConfig | None = None,
) -> list[dict[str, Any]]:
    workspace = workspace or FactorLabWorkspaceConfig()
    job = get_factor_lab_job(job_id, workspace)
    if not job:
        return []
    items: list[dict[str, Any]] = []
    for kind, (name, label) in ARTIFACT_LABELS.items():
        path = resolve_artifact_path(job_id, kind, factor_name=factor_name, workspace=workspace)
        if path is None:
            continue
        items.append(
            {
                "kind": kind,
                "name": name,
                "label": label,
                "artifact_status": "generated" if path.exists() else "missing",
                "url": artifact_url(job_id, kind, factor_name=factor_name),
            }
        )
    return items


def resolve_artifact_path(
    job_id: str,
    kind: str,
    *,
    factor_name: str | None = None,
    workspace: FactorLabWorkspaceConfig | None = None,
) -> Path | None:
    workspace = workspace or FactorLabWorkspaceConfig()
    job = get_factor_lab_job(job_id, workspace)
    if not job:
        return None

    artifacts = job.get("artifacts", {})
    path_str: str | None = None
    if kind == "proof" and factor_name:
        path_str = artifacts.get("proofs", {}).get(factor_name)
    elif kind == "truth_compare" and factor_name:
        path_str = artifacts.get("truth_compares", {}).get(factor_name)
    else:
        path_str = artifacts.get(kind)

    if not path_str:
        return None

    path = Path(path_str).resolve()
    allowed_roots = [workspace.runtime_root.resolve(), workspace.data_root.resolve()]
    if not any(path == root or root in path.parents for root in allowed_roots):
        return None
    return path
