from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from contracts.factor_research import DataSourceSpec, PanelRequest, PanelSnapshot
from research_core.data_loader.amazingdata import (
    AmazingDataConfig,
    build_data_quality_report,
    build_panel_snapshot,
    check_connection,
    fetch_amazingdata_panel,
    parse_symbol_list,
)
from research_core.factor_lab.demo_data import build_alpha101_demo_panel
from research_core.factor_lab.evaluation import build_alpha101_evaluation_report, build_factor_evaluation_report
from research_core.factor_lab.internal_validation import summarize_internal_validation, write_internal_validation_report
from research_core.factor_lab.libraries.factor_sets import (
    compute_factor_set,
    factor_set_library_name,
    factor_set_specs,
)
from research_core.factor_lab.libraries.alpha101 import (
    IMPLEMENTED_ALPHA101_FACTORS,
    alpha101_specs,
    compute_alpha101_factors,
)
from research_core.factor_lab.reporting import (
    build_alpha101_research_report,
    build_factor_research_report,
    render_alpha101_research_report_markdown,
    render_factor_research_report_markdown,
)
from research_core.factor_lab.registry import export_library_specs
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig, now_iso
from research_core.factor_lab.truth import (
    export_truth_comparison,
    load_truth_frame,
    summarize_truth_frame,
    validate_truth_frame,
)
from research_core.factor_lab.validation import export_proof_template, export_validation_report
from research_core.factor_lab.diagnostics import MismatchDiagnostician
from research_core.factor_lab.nc_classifier import NCClassifier


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _alpha101_spec_map() -> dict[str, Any]:
    return {spec.factor_name: spec for spec in alpha101_specs()}


def _spec_map(specs: list[Any]) -> dict[str, Any]:
    return {spec.factor_name: spec for spec in specs}


def _resolve_factor_names(factor_names: list[str] | None) -> list[str]:
    requested = factor_names or list(IMPLEMENTED_ALPHA101_FACTORS)
    invalid = [name for name in requested if name not in IMPLEMENTED_ALPHA101_FACTORS]
    if invalid:
        raise ValueError(f"Unsupported Alpha101 demo research factors: {invalid}")
    return requested


def _resolve_factor_set_names(factor_set: str, factor_names: list[str] | None) -> list[str]:
    specs = factor_set_specs(factor_set)
    available = [spec.factor_name for spec in specs]
    requested = factor_names or available
    invalid = [name for name in requested if name not in available]
    if invalid:
        raise ValueError(f"Unsupported {factor_set} research factors: {invalid}")
    return requested


def _render_evaluation_markdown(report: dict[str, Any], *, factor_names: list[str]) -> str:
    lines = [
        f"# {report.get('library', 'Alpha101')} Evaluation Report",
        "",
        f"- Generated at: {now_iso()}",
        f"- Dataset rows: {report['dataset']['rows']}",
        f"- Securities: {report['dataset']['codes']}",
        f"- Dates: {report['dataset']['dates']}",
        "",
        "| Factor | Coverage | Rank IC Mean | Rank IC IR | Long-Short Mean |",
        "|---|---:|---:|---:|---:|",
    ]
    for factor_name in factor_names:
        metrics = report["summary"]["metrics"][factor_name]
        lines.append(
            f"| {factor_name} | {metrics['coverage_ratio']:.4f} | "
            f"{metrics['rank_ic_mean']:.6f} | {metrics['rank_ic_ir']:.6f} | {metrics['long_short_mean']:.6f} |"
        )
    return "\n".join(lines) + "\n"


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _quality_messages(quality: Any) -> str:
    issues = getattr(quality, "issues", [])
    if not issues:
        return "none"
    return "; ".join(f"{item.severity}:{item.check}:{item.message}" for item in issues)


def _trim_to_requested_window(
    panel: pd.DataFrame,
    factor_frame: pd.DataFrame,
    dataset: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    start = str(dataset.get("start", "") or "").strip()
    end = str(dataset.get("end", "") or "").strip()
    if not start or not end:
        return panel, factor_frame, {}

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    trimmed_panel = panel.copy()
    trimmed_factor_frame = factor_frame.copy()
    trimmed_panel["date"] = pd.to_datetime(trimmed_panel["date"])
    trimmed_factor_frame["date"] = pd.to_datetime(trimmed_factor_frame["date"])

    panel_mask = (trimmed_panel["date"] >= start_ts) & (trimmed_panel["date"] <= end_ts)
    factor_mask = (trimmed_factor_frame["date"] >= start_ts) & (trimmed_factor_frame["date"] <= end_ts)
    trimmed_panel = trimmed_panel.loc[panel_mask].reset_index(drop=True)
    trimmed_factor_frame = trimmed_factor_frame.loc[factor_mask].reset_index(drop=True)
    if trimmed_panel.empty or trimmed_factor_frame.empty:
        raise ValueError(f"No validation rows remain after trimming to requested window [{start}, {end}].")

    metadata = {
        "validation_start": start,
        "validation_end": end,
        "warmup_rows": int(len(panel) - len(trimmed_panel)),
        "warmup_dates": int(panel["date"].nunique() - trimmed_panel["date"].nunique()),
        "validation_rows": int(len(trimmed_panel)),
        "validation_dates": int(trimmed_panel["date"].nunique()),
    }
    return trimmed_panel, trimmed_factor_frame, metadata


def check_amazingdata(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_payload = payload or {}
    config = (
        AmazingDataConfig.from_env_file(request_payload["env_file"])
        if request_payload.get("env_file")
        else AmazingDataConfig.from_env_file()
    )
    result = check_connection(config)
    result["env_file"] = str(request_payload.get("env_file") or "")
    return result


def _load_panel_for_job(
    request_payload: dict[str, Any],
    *,
    workspace: FactorLabWorkspaceConfig,
    job_id: str,
    default_n_dates: int,
    default_n_codes: int,
    default_seed: int,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, str]]:
    data_source = str(request_payload.get("data_source", "demo")).lower()
    artifacts: dict[str, str] = {}

    if data_source == "demo":
        n_dates = int(request_payload.get("n_dates", default_n_dates))
        n_codes = int(request_payload.get("n_codes", default_n_codes))
        seed = int(request_payload.get("seed", default_seed))
        panel = build_alpha101_demo_panel(n_dates=n_dates, n_codes=n_codes, seed=seed)
        if "vwap" not in panel.columns:
            panel["vwap"] = panel["amount"] / panel["volume"].replace(0, pd.NA)
        quality = build_data_quality_report(panel, source="demo")
        request = PanelRequest(data_source="demo", start="", end="", universe="synthetic", max_symbols=n_codes)
        snapshot = PanelSnapshot(
            request=request,
            source=DataSourceSpec(name="demo", kind="synthetic", description="Deterministic factor_lab panel."),
            quality=quality,
            rows=int(len(panel)),
            n_codes=int(panel["code"].nunique()),
            n_dates=int(panel["date"].nunique()),
            metadata={"seed": seed},
        )
        dataset = {
            "data_source": "demo",
            "n_dates": n_dates,
            "n_codes": n_codes,
            "seed": seed,
            "quality_status": quality.status,
        }
    elif data_source == "amazingdata":
        start = str(request_payload.get("start") or request_payload.get("start_date") or "").strip()
        end = str(request_payload.get("end") or request_payload.get("end_date") or "").strip()
        if not start or not end:
            raise ValueError("amazingdata jobs require start and end dates.")
        env_file = request_payload.get("env_file") or request_payload.get("config_path")
        config = AmazingDataConfig.from_env_file(env_file) if env_file else AmazingDataConfig.from_env_file()
        symbols = parse_symbol_list(request_payload.get("symbols"))
        panel, quality = fetch_amazingdata_panel(
            start=start,
            end=end,
            universe=str(request_payload.get("universe", "csi800")),
            symbols=symbols,
            max_symbols=request_payload.get("max_symbols", request_payload.get("n_codes", 300)),
            warmup_calendar_days=int(request_payload.get("warmup_calendar_days", 420)),
            min_symbol_coverage=float(request_payload.get("min_symbol_coverage", 0.95)),
            config=config,
        )
        request = PanelRequest(
            data_source="amazingdata",
            start=start,
            end=end,
            universe=str(request_payload.get("universe", "csi800")),
            symbols=symbols,
            warmup_calendar_days=int(request_payload.get("warmup_calendar_days", 420)),
            max_symbols=request_payload.get("max_symbols", request_payload.get("n_codes", 300)),
        )
        snapshot = build_panel_snapshot(request, quality, config=config)
        dataset = {
            "data_source": "amazingdata",
            "start": start,
            "end": end,
            "universe": request.universe,
            "symbols": len(symbols),
            "rows": int(len(panel)),
            "codes": int(panel["code"].nunique()),
            "dates": int(panel["date"].nunique()),
            "quality_status": quality.status,
        }
    else:
        raise ValueError("Unsupported data_source. Use 'demo' or 'amazingdata'.")

    quality_path = workspace.report_path(f"{job_id}_data_quality", suffix=".json")
    snapshot_path = workspace.report_path(f"{job_id}_panel_snapshot", suffix=".json")
    artifacts["data_quality_json"] = _write_json(quality_path, asdict(quality))
    artifacts["panel_snapshot_json"] = _write_json(snapshot_path, asdict(snapshot))
    if quality.status == "failed":
        raise ValueError(f"Data quality failed for {data_source}: {_quality_messages(quality)}")
    return panel, dataset, artifacts


def export_alpha101_truth_template(
    payload: dict[str, Any] | None = None,
    config: FactorLabWorkspaceConfig | None = None,
) -> dict[str, Any]:
    request_payload = payload or {}
    workspace = config or FactorLabWorkspaceConfig()
    workspace.ensure_directories()

    factor_names = _resolve_factor_names(request_payload.get("factor_names"))
    n_dates = int(request_payload.get("n_dates", 160))
    n_codes = int(request_payload.get("n_codes", 8))
    seed = int(request_payload.get("seed", 7))
    template_name = request_payload.get("template_name") or f"alpha101_truth_template_{len(factor_names)}f_{n_dates}d_{n_codes}c_s{seed}"
    source_label = request_payload.get("source_label", "demo_reference_template")

    panel = build_alpha101_demo_panel(n_dates=n_dates, n_codes=n_codes, seed=seed)
    truth_frame = compute_alpha101_factors(panel, factor_names=factor_names).copy()
    truth_summary = summarize_truth_frame(truth_frame, factor_names=factor_names)
    truth_frame["date"] = truth_frame["date"].dt.strftime("%Y-%m-%d")

    csv_path = workspace.data_root / f"{template_name}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    truth_frame.to_csv(csv_path, index=False, encoding="utf-8")

    manifest = {
        "library": "Alpha101",
        "kind": "truth_csv_template",
        "generated_at": now_iso(),
        "source_label": source_label,
        "template_name": template_name,
        "schema": {
            "layout": "wide",
            "row_granularity": "date_code_panel",
            "required_columns": ["date", "code", *factor_names],
            "date_format": "YYYY-MM-DD",
            "notes": [
                "每一行对应一个 date-code 面板点位。",
                "因子列名必须与 factor_lab 中的 factor_name 完全一致。",
                "如需做外部真值证明，请用真实参考结果替换模板中的因子值，不要直接回填当前实现输出。",
            ],
        },
        "summary": truth_summary,
        "artifacts": {
            "truth_csv": str(csv_path),
        },
    }
    manifest_path = workspace.report_path(f"{template_name}_manifest", suffix=".json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "library": "Alpha101",
        "template_name": template_name,
        "factor_count": len(factor_names),
        "truth_csv_path": str(csv_path),
        "manifest_path": str(manifest_path),
        "dataset": {
            "n_dates": n_dates,
            "n_codes": n_codes,
            "seed": seed,
        },
    }


def validate_alpha101_truth_csv(
    payload: dict[str, Any] | None = None,
    config: FactorLabWorkspaceConfig | None = None,
) -> dict[str, Any]:
    request_payload = payload or {}
    workspace = config or FactorLabWorkspaceConfig()
    workspace.ensure_directories()

    factor_names = _resolve_factor_names(request_payload.get("factor_names"))
    truth_csv_path = str(request_payload.get("truth_csv_path", "")).strip()
    if not truth_csv_path:
        raise ValueError("Alpha101 truth validation requires truth_csv_path.")

    truth_frame = load_truth_frame(truth_csv_path, factor_names=factor_names)
    validation = validate_truth_frame(truth_frame, factor_names=factor_names)
    return {
        "library": "Alpha101",
        "truth_csv_path": truth_csv_path,
        "requested_factor_count": len(factor_names),
        "validation": validation,
    }


def get_factor_lab_overview(config: FactorLabWorkspaceConfig | None = None) -> dict[str, Any]:
    workspace = config or FactorLabWorkspaceConfig()
    workspace.ensure_directories()
    specs = alpha101_specs()
    implemented = [spec for spec in specs if spec.metadata.get("status") == "implemented"]
    return {
        "generated_at": now_iso(),
        "libraries": [
            {
                "library": "Alpha101",
                "catalog_name": "alpha101",
                "spec_count": len(specs),
                "implemented_count": len(implemented),
                "planned_count": len(specs) - len(implemented),
                "runtime_root": str(workspace.runtime_root),
                "status": "active-template",
            },
            {
                "library": "Alpha191",
                "catalog_name": "alpha191",
                "spec_count": len(factor_set_specs("gtja191")),
                "implemented_count": len(factor_set_specs("gtja191")),
                "planned_count": 0,
                "runtime_root": str(workspace.runtime_root),
                "status": "active-incremental",
                "notes": "GTJA191 Alpha#1-#10 已接入统一 factor_lab specs/registry/service/truth/proof/report/CLI。",
            },
            {
                "library": "Alpha158",
                "catalog_name": "alpha158",
                "spec_count": len(factor_set_specs("alpha158")),
                "implemented_count": len(factor_set_specs("alpha158")),
                "planned_count": 0,
                "runtime_root": str(workspace.runtime_root),
                "status": "active-implemented",
                "notes": "158 factors integrated, verified against Qlib truth (17 exact+100 high+25 basic). Supports factor_sets.",
            },
            {
                "library": "Barra",
                "catalog_name": "barra",
                "status": "planned-bridge",
                "notes": "待引入真实财务字段口径和风险因子真值。",
            },
        ],
    }


def list_alpha101_factors(config: FactorLabWorkspaceConfig | None = None) -> list[dict[str, Any]]:
    workspace = config or FactorLabWorkspaceConfig()
    workspace.ensure_directories()
    items: list[dict[str, Any]] = []
    for spec in alpha101_specs():
        proof = _read_json_if_exists(workspace.proof_path(spec.library, spec.factor_name))
        items.append(
            {
                "factor_name": spec.factor_name,
                "display_name": spec.display_name,
                "factor_id": spec.factor_id,
                "status": spec.metadata.get("status", "unknown"),
                "implementation_stage": spec.metadata.get("implementation_stage", "unknown"),
                "required_fields": spec.required_fields,
                "has_formula": bool(spec.formula),
                "proof_status": proof.get("status") if proof else "missing",
            }
        )
    return items


def list_factor_set_factors(factor_set: str, config: FactorLabWorkspaceConfig | None = None) -> list[dict[str, Any]]:
    workspace = config or FactorLabWorkspaceConfig()
    workspace.ensure_directories()
    items: list[dict[str, Any]] = []
    for spec in factor_set_specs(factor_set):
        proof = _read_json_if_exists(workspace.proof_path(spec.library, spec.factor_name))
        items.append(
            {
                "factor_name": spec.factor_name,
                "display_name": spec.display_name,
                "factor_id": spec.factor_id,
                "library": spec.library,
                "status": spec.metadata.get("status", "unknown"),
                "implementation_stage": spec.metadata.get("implementation_stage", "unknown"),
                "required_fields": spec.required_fields,
                "has_formula": bool(spec.formula),
                "proof_status": proof.get("status") if proof else "missing",
            }
        )
    return items


def get_alpha101_factor_detail(
    factor_name: str,
    config: FactorLabWorkspaceConfig | None = None,
) -> dict[str, Any]:
    workspace = config or FactorLabWorkspaceConfig()
    workspace.ensure_directories()
    spec = _alpha101_spec_map().get(factor_name)
    if spec is None:
        raise KeyError(f"Unknown Alpha101 factor: {factor_name}")
    proof = _read_json_if_exists(workspace.proof_path(spec.library, spec.factor_name))
    return {
        "spec": asdict(spec),
        "proof": proof,
        "sample_checks": _read_json_if_exists(workspace.sample_path(spec.library, spec.factor_name)),
    }


def list_factor_lab_jobs(config: FactorLabWorkspaceConfig | None = None) -> list[dict[str, Any]]:
    workspace = config or FactorLabWorkspaceConfig()
    paths = sorted((workspace.runtime_root / "jobs").glob("*.json"), reverse=True)
    items: list[dict[str, Any]] = []
    for path in paths:
        payload = _read_json_if_exists(path)
        if payload is not None:
            items.append(payload)
    return items


def get_factor_lab_job(job_id: str, config: FactorLabWorkspaceConfig | None = None) -> dict[str, Any] | None:
    workspace = config or FactorLabWorkspaceConfig()
    return _read_json_if_exists(workspace.job_path(job_id))


def run_alpha101_research_job(
    payload: dict[str, Any] | None = None,
    config: FactorLabWorkspaceConfig | None = None,
) -> dict[str, Any]:
    request_payload = payload or {}
    workspace = config or FactorLabWorkspaceConfig()
    workspace.ensure_directories()

    factor_names = _resolve_factor_names(request_payload.get("factor_names"))
    n_dates = int(request_payload.get("n_dates", 160))
    n_codes = int(request_payload.get("n_codes", 8))
    seed = int(request_payload.get("seed", 7))
    data_source = request_payload.get("data_source", "demo")
    truth_csv_path = request_payload.get("truth_csv_path", "")
    truth_tolerance = float(request_payload.get("truth_tolerance", 1e-12))

    specs = alpha101_specs()
    export_library_specs(config=workspace, library="alpha101", specs=specs)

    job_id = request_payload.get("job_id") or f"alpha101-{uuid4().hex[:12]}"
    panel, dataset, data_artifacts = _load_panel_for_job(
        request_payload,
        workspace=workspace,
        job_id=job_id,
        default_n_dates=n_dates,
        default_n_codes=n_codes,
        default_seed=seed,
    )
    factor_frame = compute_alpha101_factors(panel, factor_names=factor_names)
    validation_panel, validation_factor_frame, validation_window = _trim_to_requested_window(panel, factor_frame, dataset)
    dataset.update(validation_window)
    evaluation_report = build_alpha101_evaluation_report(validation_panel, validation_factor_frame, factor_names=factor_names)
    internal_report = summarize_internal_validation(
        validation_panel,
        validation_factor_frame,
        factor_names=factor_names,
        horizon=int(request_payload.get("horizon", 1)),
        quantiles=int(request_payload.get("quantiles", 5)),
    )
    truth_frame = load_truth_frame(truth_csv_path, factor_names=factor_names) if truth_csv_path else None
    truth_summary = summarize_truth_frame(truth_frame, factor_names=factor_names) if truth_frame is not None else {}

    frame_path = workspace.frame_path("alpha101", job_id)
    validation_factor_frame.to_csv(frame_path, index=False, encoding="utf-8")

    evaluation_json_path = workspace.report_path(f"{job_id}_evaluation", suffix=".json")
    evaluation_json_path.write_text(json.dumps(evaluation_report, ensure_ascii=False, indent=2), encoding="utf-8")
    evaluation_md_path = workspace.report_path(f"{job_id}_evaluation", suffix=".md")
    evaluation_md_path.write_text(
        _render_evaluation_markdown(evaluation_report, factor_names=factor_names),
        encoding="utf-8",
    )
    internal_validation_json_path = workspace.report_path(f"{job_id}_internal_validation", suffix=".json")
    write_internal_validation_report(internal_report, internal_validation_json_path)

    spec_map = _alpha101_spec_map()
    proof_paths: dict[str, str] = {}
    proof_payloads: dict[str, dict[str, Any]] = {}
    truth_paths: dict[str, str] = {}
    truth_payloads: dict[str, dict[str, Any]] = {}
    for factor_name in factor_names:
        factor_only_frame = validation_factor_frame[["date", "code", factor_name]].copy()
        truth_path = ""
        truth_metrics: dict[str, Any] | None = None
        if truth_frame is not None:
            truth_path, truth_metrics = export_truth_comparison(
                config=workspace,
                spec=spec_map[factor_name],
                factor_frame=factor_only_frame,
                truth_frame=truth_frame,
                tolerance=truth_tolerance,
            )
            truth_paths[factor_name] = truth_path
            truth_payloads[factor_name] = truth_metrics
        proof_paths[factor_name] = export_validation_report(
            config=workspace,
            spec=spec_map[factor_name],
            factor_frame=factor_only_frame,
            evaluation_report=evaluation_report,
            available_columns=validation_panel.columns.tolist(),
            evaluation_path=str(evaluation_json_path),
            job_id=job_id,
            truth_path=truth_path,
            truth_metrics=truth_metrics,
        )
        proof_payloads[factor_name] = json.loads(Path(proof_paths[factor_name]).read_text(encoding="utf-8"))

    for spec in specs:
        if spec.factor_name not in proof_paths:
            export_proof_template(config=workspace, spec=spec)

    research_report = build_alpha101_research_report(
        job_id=job_id,
        factor_names=factor_names,
        evaluation_report=evaluation_report,
        proof_payloads=proof_payloads,
        truth_payloads=truth_payloads,
        data_source=data_source,
    )
    research_report_json_path = workspace.report_path(f"{job_id}_proof_report", suffix=".json")
    research_report_json_path.write_text(
        json.dumps(research_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    research_report_md_path = workspace.report_path(f"{job_id}_proof_report", suffix=".md")
    research_report_md_path.write_text(
        render_alpha101_research_report_markdown(research_report),
        encoding="utf-8",
    )

    job = {
        "job_id": job_id,
        "library": "Alpha101",
        "status": "completed",
        "data_source": data_source,
        "truth_csv_path": truth_csv_path,
        "truth_enabled": bool(truth_csv_path),
        "truth_summary": truth_summary,
        "generated_at": now_iso(),
        "requested_factors": factor_names,
        "dataset": dataset,
        "artifacts": {
            **data_artifacts,
            "factor_frame": str(frame_path),
            "evaluation_json": str(evaluation_json_path),
            "evaluation_markdown": str(evaluation_md_path),
            "internal_validation_json": str(internal_validation_json_path),
            "research_report_json": str(research_report_json_path),
            "research_report_markdown": str(research_report_md_path),
            "proofs": proof_paths,
            "truth_compares": truth_paths,
            "catalog": str(workspace.catalog_path("alpha101")),
            "specs": str(workspace.specs_path("alpha101")),
        },
    }
    workspace.job_path(job_id).write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return job


def run_factor_set_research_job(
    payload: dict[str, Any] | None = None,
    config: FactorLabWorkspaceConfig | None = None,
) -> dict[str, Any]:
    request_payload = payload or {}
    workspace = config or FactorLabWorkspaceConfig()
    workspace.ensure_directories()

    factor_set = str(request_payload.get("factor_set", "wq101")).lower()
    factor_names = _resolve_factor_set_names(factor_set, request_payload.get("factor_names"))
    n_dates = int(request_payload.get("n_dates", 160))
    n_codes = int(request_payload.get("n_codes", 8))
    seed = int(request_payload.get("seed", 7))
    data_source = request_payload.get("data_source", "demo")
    truth_csv_path = request_payload.get("truth_csv_path", "")
    truth_tolerance = float(request_payload.get("truth_tolerance", 1e-12))

    specs = factor_set_specs(factor_set)
    library = factor_set_library_name(factor_set)
    catalog_key = factor_set
    export_library_specs(config=workspace, library=catalog_key, specs=specs)

    job_id = request_payload.get("job_id") or f"{factor_set}-{uuid4().hex[:12]}"
    panel, dataset, data_artifacts = _load_panel_for_job(
        request_payload,
        workspace=workspace,
        job_id=job_id,
        default_n_dates=n_dates,
        default_n_codes=n_codes,
        default_seed=seed,
    )
    factor_frame = compute_factor_set(panel, factor_set, factor_names=factor_names)
    validation_panel, validation_factor_frame, validation_window = _trim_to_requested_window(panel, factor_frame, dataset)
    dataset.update(validation_window)
    evaluation_report = build_factor_evaluation_report(
        validation_panel,
        validation_factor_frame,
        factor_names=factor_names,
        library=library,
    )
    internal_report = summarize_internal_validation(
        validation_panel,
        validation_factor_frame,
        factor_names=factor_names,
        horizon=int(request_payload.get("horizon", 1)),
        quantiles=int(request_payload.get("quantiles", 5)),
    )
    truth_frame = load_truth_frame(truth_csv_path, factor_names=factor_names) if truth_csv_path else None
    truth_summary = summarize_truth_frame(truth_frame, factor_names=factor_names) if truth_frame is not None else {}

    frame_path = workspace.frame_path(catalog_key, job_id)
    validation_factor_frame.to_csv(frame_path, index=False, encoding="utf-8")

    evaluation_json_path = workspace.report_path(f"{job_id}_evaluation", suffix=".json")
    evaluation_json_path.write_text(json.dumps(evaluation_report, ensure_ascii=False, indent=2), encoding="utf-8")
    evaluation_md_path = workspace.report_path(f"{job_id}_evaluation", suffix=".md")
    evaluation_md_path.write_text(_render_evaluation_markdown(evaluation_report, factor_names=factor_names), encoding="utf-8")
    internal_validation_json_path = workspace.report_path(f"{job_id}_internal_validation", suffix=".json")
    write_internal_validation_report(internal_report, internal_validation_json_path)

    specs_by_name = _spec_map(specs)
    proof_paths: dict[str, str] = {}
    proof_payloads: dict[str, dict[str, Any]] = {}
    truth_paths: dict[str, str] = {}
    truth_payloads: dict[str, dict[str, Any]] = {}
    for factor_name in factor_names:
        factor_only_frame = validation_factor_frame[["date", "code", factor_name]].copy()
        truth_path = ""
        truth_metrics: dict[str, Any] | None = None
        if truth_frame is not None:
            truth_path, truth_metrics = export_truth_comparison(
                config=workspace,
                spec=specs_by_name[factor_name],
                factor_frame=factor_only_frame,
                truth_frame=truth_frame,
                tolerance=truth_tolerance,
            )
            truth_paths[factor_name] = truth_path
            truth_payloads[factor_name] = truth_metrics
        proof_paths[factor_name] = export_validation_report(
            config=workspace,
            spec=specs_by_name[factor_name],
            factor_frame=factor_only_frame,
            evaluation_report=evaluation_report,
            available_columns=validation_panel.columns.tolist(),
            evaluation_path=str(evaluation_json_path),
            job_id=job_id,
            truth_path=truth_path,
            truth_metrics=truth_metrics,
        )
        proof_payloads[factor_name] = json.loads(Path(proof_paths[factor_name]).read_text(encoding="utf-8"))

    for spec in specs:
        if spec.factor_name not in proof_paths:
            export_proof_template(config=workspace, spec=spec)

    research_report = build_factor_research_report(
        job_id=job_id,
        library=library,
        factor_names=factor_names,
        evaluation_report=evaluation_report,
        proof_payloads=proof_payloads,
        truth_payloads=truth_payloads,
        data_source=data_source,
    )
    research_report_json_path = workspace.report_path(f"{job_id}_proof_report", suffix=".json")
    research_report_json_path.write_text(json.dumps(research_report, ensure_ascii=False, indent=2), encoding="utf-8")
    research_report_md_path = workspace.report_path(f"{job_id}_proof_report", suffix=".md")
    research_report_md_path.write_text(render_factor_research_report_markdown(research_report), encoding="utf-8")

    job = {
        "job_id": job_id,
        "library": library,
        "factor_set": factor_set,
        "status": "completed",
        "data_source": data_source,
        "truth_csv_path": truth_csv_path,
        "truth_enabled": bool(truth_csv_path),
        "truth_summary": truth_summary,
        "generated_at": now_iso(),
        "requested_factors": factor_names,
        "dataset": dataset,
        "artifacts": {
            **data_artifacts,
            "factor_frame": str(frame_path),
            "evaluation_json": str(evaluation_json_path),
            "evaluation_markdown": str(evaluation_md_path),
            "internal_validation_json": str(internal_validation_json_path),
            "research_report_json": str(research_report_json_path),
            "research_report_markdown": str(research_report_md_path),
            "proofs": proof_paths,
            "truth_compares": truth_paths,
            "catalog": str(workspace.catalog_path(catalog_key)),
            "specs": str(workspace.specs_path(catalog_key)),
        },
    }
    workspace.job_path(job_id).write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return job


def run_alpha101_truth_proof_batch(
    payload: dict[str, Any] | None = None,
    config: FactorLabWorkspaceConfig | None = None,
) -> dict[str, Any]:
    request_payload = dict(payload or {})
    truth_csv_path = str(request_payload.get("truth_csv_path", "")).strip()
    if not truth_csv_path:
        raise ValueError("Alpha101 truth proof batch requires truth_csv_path.")

    request_payload.setdefault("factor_names", list(IMPLEMENTED_ALPHA101_FACTORS))
    request_payload.setdefault("n_dates", 420)
    request_payload.setdefault("n_codes", 8)
    request_payload.setdefault("seed", 29)
    request_payload.setdefault("data_source", "demo")

    job = run_alpha101_research_job(request_payload, config=config)
    report_path = Path(job["artifacts"]["research_report_json"])
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "job_id": job["job_id"],
        "library": job["library"],
        "status": job["status"],
        "truth_csv_path": truth_csv_path,
        "requested_factor_count": len(job["requested_factors"]),
        "proof_batch_summary": report_payload["summary"],
        "artifacts": job["artifacts"],
    }


# ══════════════════════════════════════════════════════════════════
#  jq_gm service wrappers (added Week 2)
# ══════════════════════════════════════════════════════════════════
#
# These follow the same shape as alpha101 service functions, but use
# jq_gm specs and compute instead of alpha101.  The core workflow
# (panel → compute → evaluate → proof → report) is identical; only
# the spec source and compute function differ.

from research_core.factor_lab.libraries.jq_gm import (
    JQ_GM_IMPLEMENTED_FACTORS,
    jq_gm_specs,
)
from research_core.factor_lab.libraries.jq_gm.factors import (
    compute_jq_gm_factors,
)


def _resolve_jq_gm_factor_names(factor_names: list[str] | None) -> list[str]:
    """Validate and resolve jq_gm factor names against the implemented set."""
    requested = factor_names or list(JQ_GM_IMPLEMENTED_FACTORS)
    invalid = [name for name in requested if name not in JQ_GM_IMPLEMENTED_FACTORS]
    if invalid:
        raise ValueError(
            f"Unsupported jq_gm factors: {invalid}. "
            f"Use list-jq-gm to see available factors."
        )
    return requested


def list_jq_gm_factors(
    config: FactorLabWorkspaceConfig | None = None,
) -> list[dict[str, Any]]:
    """List all jq_gm factors with their proof status.

    Same shape as list_alpha101_factors() — used by the list-jq-gm
    CLI command and the factor_lab overview dashboard.
    """
    workspace = config or FactorLabWorkspaceConfig()
    workspace.ensure_directories()
    items: list[dict[str, Any]] = []
    for spec in jq_gm_specs():
        proof = _read_json_if_exists(
            workspace.proof_path(spec.library, spec.factor_name)
        )
        items.append({
            "factor_name": spec.factor_name,
            "display_name": spec.display_name,
            "category": spec.tags[0] if spec.tags else "",
            "required_fields": spec.required_fields,
            "gm_field": spec.metadata.get("gm_field", ""),
            "has_formula": bool(spec.formula),
            "proof_status": proof.get("status") if proof else "missing",
        })
    return items


def run_jq_gm_research_job(
    payload: dict[str, Any] | None = None,
    config: FactorLabWorkspaceConfig | None = None,
) -> dict[str, Any]:
    """Run a jq_gm factor research job (demo or truth-backed).

    Reuses the same 6-step pipeline as run_alpha101_research_job():
      1. Demo panel generation
      2. Factor computation (via compute_jq_gm_factors)
      3. Evaluation metrics (IC, coverage, etc.)
      4. Per-factor proof reports
      5. Aggregated research report
      6. Job metadata

    In GM-stub mode (no GM SDK), step 2 returns NaN-filled frames,
    sufficient for pipeline validation but not numerical correctness.
    """
    request_payload = payload or {}
    workspace = config or FactorLabWorkspaceConfig()
    workspace.ensure_directories()

    factor_names = _resolve_jq_gm_factor_names(
        request_payload.get("factor_names")
    )
    n_dates = int(request_payload.get("n_dates", 160))
    n_codes = int(request_payload.get("n_codes", 8))
    seed = int(request_payload.get("seed", 7))
    data_source = request_payload.get("data_source", "demo")
    truth_csv_path = request_payload.get("truth_csv_path", "")
    truth_tolerance = float(request_payload.get("truth_tolerance", 1e-12))

    if data_source != "demo":
        raise ValueError(
            "jq_gm research jobs currently support 'demo' data_source only."
        )

    specs = jq_gm_specs()
    export_library_specs(config=workspace, library="jq_gm", specs=specs)

    job_id = request_payload.get("job_id") or f"jq_gm-{uuid4().hex[:12]}"
    panel = build_alpha101_demo_panel(n_dates=n_dates, n_codes=n_codes, seed=seed)
    factor_frame = compute_jq_gm_factors(panel, factor_names=factor_names)

    eval_report = build_factor_evaluation_report(
        panel, factor_frame, factor_names=factor_names, library="jq_gm"
    )
    truth_frame = (
        load_truth_frame(truth_csv_path, factor_names=factor_names)
        if truth_csv_path else None
    )
    truth_summary = (
        summarize_truth_frame(truth_frame, factor_names=factor_names)
        if truth_frame is not None else {}
    )

    frame_path = workspace.frame_path("jq_gm", job_id)
    factor_frame.to_csv(frame_path, index=False, encoding="utf-8")

    eval_json_path = workspace.report_path(f"{job_id}_evaluation", suffix=".json")
    eval_json_path.write_text(
        json.dumps(eval_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    eval_md_path = workspace.report_path(f"{job_id}_evaluation", suffix=".md")
    eval_md_path.write_text(
        _render_evaluation_markdown(eval_report, factor_names=factor_names),
        encoding="utf-8",
    )

    specs_by_name = _spec_map(specs)
    proof_paths: dict[str, str] = {}
    proof_payloads: dict[str, dict[str, Any]] = {}
    truth_paths: dict[str, str] = {}
    truth_payloads: dict[str, dict[str, Any]] = {}

    for factor_name in factor_names:
        factor_only = factor_frame[["date", "code", factor_name]].copy()
        truth_path = ""
        truth_metrics: dict[str, Any] | None = None
        if truth_frame is not None:
            truth_path, truth_metrics = export_truth_comparison(
                config=workspace,
                spec=specs_by_name[factor_name],
                factor_frame=factor_only,
                truth_frame=truth_frame,
                tolerance=truth_tolerance,
            )
            truth_paths[factor_name] = truth_path
            truth_payloads[factor_name] = truth_metrics

        proof_paths[factor_name] = export_validation_report(
            config=workspace,
            spec=specs_by_name[factor_name],
            factor_frame=factor_only,
            evaluation_report=eval_report,
            available_columns=panel.columns.tolist(),
            evaluation_path=str(eval_json_path),
            job_id=job_id,
            truth_path=truth_path,
            truth_metrics=truth_metrics,
        )
        proof_payloads[factor_name] = json.loads(
            Path(proof_paths[factor_name]).read_text(encoding="utf-8")
        )

    # Generate proof templates for factors not in this run.
    for spec in specs:
        if spec.factor_name not in proof_paths:
            export_proof_template(config=workspace, spec=spec)

    # ── NC classification + diagnostics (W3-4) ──
    nc_result = None
    diagnosis_results = {}
    nc_report_path = workspace.report_path(f"{job_id}_nc", suffix=".md")
    diag_report_path = workspace.report_path(f"{job_id}_diagnosis", suffix=".json")
    if truth_frame is not None and truth_payloads:
        import pandas as _pd
        rows = []
        for fn in factor_names:
            tp = truth_payloads.get(fn, {})
            for mm in tp.get("mismatches", []):
                rows.append({
                    "factor_key": fn,
                    "symbol": mm.get("code", mm.get("symbol", "")),
                    "gm_value": mm.get("computed_value", float("nan")),
                    "jq_value": mm.get("truth_value", float("nan")),
                    "diff_pct": mm.get("abs_error", 0.0),
                    "status": "MISMATCH",
                })
        if rows:
            cmp_df = _pd.DataFrame(rows)
            reg = {s.factor_name: {
                "gm_field": s.metadata.get("gm_field", ""),
                "display_name": s.display_name,
                "ttm": s.metadata.get("ttm", False),
            } for s in specs}
            cls = NCClassifier(factor_registry=reg)
            nc_result = cls.batch_classify(cmp_df)
            diag = MismatchDiagnostician()
            diagnosis_results = {k: v.to_dict() for k, v in
                                 diag.diagnose_all(cmp_df, reg).items()}
            nc_report_path.write_text(cls.generate_report(nc_result), encoding="utf-8")
            import json as _json
            diag_report_path.write_text(_json.dumps(
                diagnosis_results, ensure_ascii=False, indent=2), encoding="utf-8")

    research_report = build_factor_research_report(
        job_id=job_id,
        library="jq_gm",
        factor_names=factor_names,
        evaluation_report=eval_report,
        proof_payloads=proof_payloads,
        truth_payloads=truth_payloads,
        data_source=data_source,
    )

    report_json_path = workspace.report_path(
        f"{job_id}_proof_report", suffix=".json"
    )
    report_json_path.write_text(
        json.dumps(research_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_md_path = workspace.report_path(
        f"{job_id}_proof_report", suffix=".md"
    )
    report_md_path.write_text(
        render_factor_research_report_markdown(research_report),
        encoding="utf-8",
    )

    job = {
        "job_id": job_id,
        "library": "jq_gm",
        "status": "completed",
        "data_source": data_source,
        "truth_csv_path": truth_csv_path,
        "truth_enabled": bool(truth_csv_path),
        "truth_summary": truth_summary,
        "nc_classification": {
            "stats": nc_result.stats if nc_result else {},
            "factor_nc": nc_result.factor_nc if nc_result else {},
        },
        "diagnostics": diagnosis_results,
        "generated_at": now_iso(),
        "requested_factors": factor_names,
        "dataset": {"n_dates": n_dates, "n_codes": n_codes, "seed": seed},
        "artifacts": {
            "factor_frame": str(frame_path),
            "evaluation_json": str(eval_json_path),
            "evaluation_markdown": str(eval_md_path),
            "research_report_json": str(report_json_path),
            "research_report_markdown": str(report_md_path),
            "proofs": proof_paths,
            "truth_compares": truth_paths,
            "catalog": str(workspace.catalog_path("jq_gm")),
            "specs": str(workspace.specs_path("jq_gm")),
            "nc_report_md": str(nc_report_path) if nc_result else "",
            "diagnosis_report_json": str(diag_report_path) if diagnosis_results else "",
        },
    }
    workspace.job_path(job_id).write_text(
        json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return job


def run_jq_gm_truth_proof_batch(
    payload: dict[str, Any] | None = None,
    config: FactorLabWorkspaceConfig | None = None,
) -> dict[str, Any]:
    """Run jq_gm proof-batch with an external truth CSV.

    Thin wrapper around run_jq_gm_research_job() that enforces
    truth_csv_path and returns a proof-batch summary.
    """
    request_payload = payload or {}
    truth_csv_path = str(request_payload.get("truth_csv_path", "")).strip()
    if not truth_csv_path:
        raise ValueError(
            "jq_gm proof-batch requires --truth-csv pointing to a "
            "valid truth CSV file."
        )

    job = run_jq_gm_research_job(request_payload, config=config)
    report_path = Path(job["artifacts"]["research_report_json"])
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))

    return {
        "job_id": job["job_id"],
        "library": job["library"],
        "status": job["status"],
        "truth_csv_path": truth_csv_path,
        "requested_factor_count": len(job["requested_factors"]),
        "proof_batch_summary": report_payload["summary"],
        "artifacts": job["artifacts"],
    }


def verify_candidates(
    expressions: list[str],
    *,
    n_dates: int = 3,
    n_codes: int = 20,
    seed: int = 42,
) -> dict[str, Any]:
    """Verify AI-generated candidate factor expressions via mining bridge."""
    from research_core.factor_lab.mining_bridge import (
        batch_verify, feedback_to_miner,
    )
    import pandas as pd, numpy as np

    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=n_dates, freq="B")
    codes = [f"C{i:04d}" for i in range(n_codes)]
    idx = pd.MultiIndex.from_product([dates, codes], names=["date", "code"])
    panel = pd.DataFrame({
        "open": rng.uniform(10, 100, len(idx)),
        "high": rng.uniform(10, 100, len(idx)),
        "low": rng.uniform(10, 100, len(idx)),
        "close": rng.uniform(10, 100, len(idx)),
        "volume": rng.uniform(1e4, 1e7, len(idx)),
        "vwap": rng.uniform(10, 100, len(idx)),
    }, index=idx).reset_index()

    results = batch_verify(expressions, panel)
    feedback = feedback_to_miner(results)

    return {
        "expressions": len(expressions),
        "results": [
            {
                "expression": r.expression,
                "status": r.status,
                "parsed_type": r.parsed.expr_type.name if r.parsed else None,
                "finite_ratio": r.finite_ratio,
            }
            for r in results
        ],
        "feedback": feedback,
    }
