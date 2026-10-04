from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research_core.factor_lab.deterministic_validation import (
    _canonical_json,
    _format_metric,
    _json_safe,
    load_validation_config,
)

DEFAULT_PRECISION = 12


@dataclass(frozen=True)
class Finding:
    scope: str
    check: str
    detail: str
    expected: str
    actual: str


class CrossCheckError(ValueError):
    """Raised when the cross-check cannot even be set up."""


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_result_hash(payload: dict[str, Any], precision: int) -> str:
    return hashlib.sha256(
        _canonical_json(_json_safe(payload, precision=precision)).encode("utf-8")
    ).hexdigest()


def _report_status_line(report_text: str) -> str:
    for line in report_text.splitlines():
        if line.startswith("status="):
            return line.strip()
    return ""


def _report_gate_names(report_text: str) -> list[str]:
    names: list[str] = []
    in_table = False
    for line in report_text.splitlines():
        if line.startswith("| Gate |"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if set(line) <= set("|-: "):
                continue
            names.append(line.split("|")[1].strip())
    return names


def _report_rank_ic_rows(report_text: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    in_table = False
    for line in report_text.splitlines():
        if line.startswith("| Horizon |"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if set(line) <= set("|-: "):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if cells:
                rows[cells[0]] = cells[1:]
    return rows


def cross_check(
    *,
    batch_manifest: str | Path,
    panel_file: str | Path | None = None,
    factor_file: str | Path | None = None,
    candidates_path: str | Path | None = None,
    factor_catalog: str | Path | None = None,
    package_manifest: str | Path | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Independently re-derive every hash and list, and report every mismatch found."""
    manifest_path = Path(batch_manifest)
    if not manifest_path.is_file():
        raise CrossCheckError(f"batch manifest does not exist: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = manifest.get("results")
    if not isinstance(results, list):
        raise CrossCheckError("batch manifest has no results list")

    precision = DEFAULT_PRECISION
    if config_path is not None:
        precision = int(load_validation_config(config_path)["output"]["float_precision"])

    findings: list[Finding] = []
    checked: dict[str, int] = {}

    def report(scope: str, check: str, detail: str, expected: Any, actual: Any) -> None:
        findings.append(Finding(scope, check, detail, str(expected), str(actual)))

    def verify_file_hash(scope: str, label: str, path: Path, declared: str | None) -> None:
        checked[label] = checked.get(label, 0) + 1
        if declared is None:
            return
        actual = _sha256_file(path)
        if actual is None:
            report(scope, f"{label}_missing", f"{label} not found", declared, path)
        elif actual != declared:
            report(scope, f"{label}_sha256", f"{label} bytes differ from the declared digest", declared, actual)

    # --- declared inputs ---
    panel_declared = manifest.get("panel_file_sha256")
    if panel_file is not None:
        verify_file_hash("batch", "panel", Path(panel_file), panel_declared)
    factor_declared = manifest.get("factor_file_sha256")
    if factor_file is not None:
        verify_file_hash("batch", "factor", Path(factor_file), factor_declared)
    candidates_declared = manifest.get("candidates_file_sha256")
    if candidates_path is not None:
        verify_file_hash("batch", "candidates", Path(candidates_path), candidates_declared)

    if config_path is not None:
        verify_file_hash(
            "batch", "config", Path(config_path), manifest.get("configuration_sha256")
        )

    code_commit = str(manifest.get("code_commit", ""))
    checked["code_commit"] = checked.get("code_commit", 0) + 1
    if len(code_commit) != 40 or any(char not in "0123456789abcdef" for char in code_commit):
        report("batch", "code_commit", "code_commit must be a 40-char hex sha", "40-hex", code_commit)

    # --- counts and name lists must agree with the per-factor statuses ---
    statuses = [str(entry.get("status")) for entry in results]
    counts = manifest.get("counts") or {}
    for status in ("validated", "rejected", "train_only", "needs_human", "error"):
        declared = counts.get(status)
        if declared is None:
            continue
        actual = statuses.count(status)
        checked["counts"] = checked.get("counts", 0) + 1
        if int(declared) != actual:
            report("batch", "counts", f"counts[{status}] does not match the results list", declared, actual)
    for label, status in (
        ("validated", "validated"),
        ("rejected", "rejected"),
        ("errors", "error"),
        ("needs_human", "needs_human"),
    ):
        declared_list = manifest.get(label)
        if declared_list is None:
            continue
        actual_list = [
            str(entry.get("factor_id")) for entry in results if str(entry.get("status")) == status
        ]
        checked["lists"] = checked.get("lists", 0) + 1
        if list(declared_list) != actual_list:
            report("batch", "factor_list", f"manifest[{label}] does not match the results list", declared_list, actual_list)

    if candidates_path is not None:
        with Path(candidates_path).open(encoding="utf-8-sig", newline="") as stream:
            candidate_ids = [row["factor_id"].strip() for row in csv.DictReader(stream)]
        checked["candidate_count"] = checked.get("candidate_count", 0) + 1
        if int(manifest.get("candidate_count", -1)) != len(candidate_ids):
            report(
                "batch",
                "candidate_count",
                "candidate_count does not match candidate_list.csv",
                len(candidate_ids),
                manifest.get("candidate_count"),
            )
        if sorted(manifest.get("factor_ids") or []) != sorted(candidate_ids):
            report(
                "batch",
                "factor_ids",
                "factor_ids does not match candidate_list.csv",
                sorted(candidate_ids),
                sorted(manifest.get("factor_ids") or []),
            )

    # --- per factor: artifact hashes, result_hash, report consistency ---
    for entry in results:
        factor_id = str(entry.get("factor_id"))
        artifacts = entry.get("artifacts") or {}
        declared_hashes = entry.get("artifact_sha256") or {}
        result_path = Path(artifacts["result"]) if artifacts.get("result") else None
        if result_path is None or not result_path.is_file():
            if entry.get("status") not in {"error", "needs_human"}:
                report(factor_id, "result_missing", "validation_result.json not found", "a file", result_path)
            continue

        for name, declared in declared_hashes.items():
            verify_file_hash(factor_id, f"{name}_artifact", Path(artifacts.get(name, "")), declared)

        payload = json.loads(result_path.read_text(encoding="utf-8"))
        recomputed = _canonical_result_hash(payload, precision)
        checked["result_hash"] = checked.get("result_hash", 0) + 1
        if entry.get("result_hash") != recomputed:
            report(
                factor_id,
                "result_hash",
                "result_hash does not match the recomputed canonical hash of validation_result.json",
                entry.get("result_hash"),
                recomputed,
            )
        if str(payload.get("status")) != str(entry.get("status")):
            report(
                factor_id,
                "status",
                "batch status does not match validation_result.json",
                entry.get("status"),
                payload.get("status"),
            )
        if str(payload.get("factor_id")) != factor_id:
            report(
                factor_id,
                "factor_id",
                "validation_result.json factor_id differs from the batch entry",
                factor_id,
                payload.get("factor_id"),
            )
        if list(payload.get("failed_gates") or []) != list(entry.get("failed_gates") or []):
            report(
                factor_id,
                "failed_gates",
                "batch failed_gates differ from validation_result.json",
                entry.get("failed_gates"),
                payload.get("failed_gates"),
            )

        report_path = Path(artifacts["report"]) if artifacts.get("report") else None
        if report_path is not None and report_path.is_file():
            text = report_path.read_text(encoding="utf-8")
            first_line = _report_status_line(text)
            checked["report"] = checked.get("report", 0) + 1
            if not first_line.startswith(f"status={payload.get('status')}"):
                report(factor_id, "report_status", "report status line contradicts the result", f"status={payload.get('status')}", first_line)
            gate_names = _report_gate_names(text)
            result_gate_names = [str(gate.get("name")) for gate in payload.get("gates") or []]
            if gate_names != result_gate_names:
                report(factor_id, "report_gates", "report gate table does not match the result gates", result_gate_names, gate_names)
            horizons = _report_rank_ic_rows(text)
            table = payload.get("rank_ic") or payload.get("train_rank_ic") or {}
            if sorted(horizons) != sorted(str(key) for key in table):
                report(
                    factor_id,
                    "report_rank_ic",
                    "report RankIC table does not match the result",
                    sorted(str(key) for key in table),
                    sorted(horizons),
                )
            else:
                for horizon, values in table.items():
                    cells = horizons.get(str(horizon), [])
                    expected = [
                        _format_metric(values.get("mean")),
                        _format_metric(values.get("ic_ir")),
                        _format_metric(values.get("t_stat")),
                        str(values.get("days")),
                    ]
                    if cells != expected:
                        report(
                            factor_id,
                            "report_rank_ic_values",
                            f"report RankIC row {horizon} does not match the result payload",
                            expected,
                            cells,
                        )

    # --- batch_summary.csv vs manifest ---
    summary_path = (manifest.get("outputs") or {}).get("batch_summary_csv")
    if summary_path and Path(summary_path).is_file():
        with Path(summary_path).open(encoding="utf-8", newline="") as stream:
            summary = {row["factor_id"]: row for row in csv.DictReader(stream)}
        for entry in results:
            factor_id = str(entry.get("factor_id"))
            row = summary.get(factor_id)
            checked["summary"] = checked.get("summary", 0) + 1
            if row is None:
                report(factor_id, "summary_row", "missing from batch_summary.csv", factor_id, "absent")
                continue
            if row["status"] != str(entry.get("status")):
                report(factor_id, "summary_status", "summary status differs from the manifest", entry.get("status"), row["status"])
            if (row.get("result_hash") or "") != (entry.get("result_hash") or ""):
                report(
                    factor_id,
                    "summary_result_hash",
                    "summary result_hash differs from the manifest",
                    entry.get("result_hash"),
                    row.get("result_hash"),
                )

    # --- factor_catalog.csv vs manifest ---
    if factor_catalog is not None:
        with Path(factor_catalog).open(encoding="utf-8", newline="") as stream:
            catalog = {row["factor_id"]: row for row in csv.DictReader(stream)}
        for entry in results:
            factor_id = str(entry.get("factor_id"))
            row = catalog.get(factor_id)
            checked["catalog"] = checked.get("catalog", 0) + 1
            if row is None:
                report(factor_id, "catalog_row", "missing from factor_catalog.csv", factor_id, "absent")
            elif row["status"] != str(entry.get("status")):
                report(factor_id, "catalog_status", "catalog status differs from the manifest", entry.get("status"), row["status"])

    # --- package_manifest.json vs manifest ---
    if package_manifest is not None:
        package = json.loads(Path(package_manifest).read_text(encoding="utf-8"))
        included = {item["factor_id"] for item in package.get("included_factors") or []}
        validated = {str(entry.get("factor_id")) for entry in results if entry.get("status") == "validated"}
        checked["package"] = checked.get("package", 0) + 1
        if included != validated:
            report("batch", "package_included", "package contents differ from the validated set", sorted(validated), sorted(included))
        for item in package.get("included_factors") or []:
            for name, record in (item.get("artifacts") or {}).items():
                source = Path(record.get("source", ""))
                copied = Path(record.get("path", ""))
                target = copied if copied.is_absolute() else Path(package_manifest).parent / copied
                source_digest = _sha256_file(source)
                target_digest = _sha256_file(target)
                checked["package_artifacts"] = checked.get("package_artifacts", 0) + 1
                if source_digest != target_digest:
                    report(
                        item["factor_id"],
                        "package_artifact",
                        f"packaged {name} differs from its source",
                        source_digest,
                        target_digest,
                    )

    return {
        "batch_manifest": str(manifest_path),
        "code_commit": code_commit,
        "precision": precision,
        "checked": checked,
        "finding_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
    }
