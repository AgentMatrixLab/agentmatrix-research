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
                "status": "planned-bridge",
                "notes": "当前以 qlib_lab 主线承载，后续接入统一规格层。",
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
    evaluation_report = build_alpha101_evaluation_report(panel, factor_frame, factor_names=factor_names)
    internal_report = summarize_internal_validation(
        panel,
        factor_frame,
        factor_names=factor_names,
        horizon=int(request_payload.get("horizon", 1)),
        quantiles=int(request_payload.get("quantiles", 5)),
    )
    truth_frame = load_truth_frame(truth_csv_path, factor_names=factor_names) if truth_csv_path else None
    truth_summary = summarize_truth_frame(truth_frame, factor_names=factor_names) if truth_frame is not None else {}

    frame_path = workspace.frame_path("alpha101", job_id)
    factor_frame.to_csv(frame_path, index=False, encoding="utf-8")

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
        factor_only_frame = factor_frame[["date", "code", factor_name]].copy()
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
            available_columns=panel.columns.tolist(),
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
    evaluation_report = build_factor_evaluation_report(panel, factor_frame, factor_names=factor_names, library=library)
    internal_report = summarize_internal_validation(
        panel,
        factor_frame,
        factor_names=factor_names,
        horizon=int(request_payload.get("horizon", 1)),
        quantiles=int(request_payload.get("quantiles", 5)),
    )
    truth_frame = load_truth_frame(truth_csv_path, factor_names=factor_names) if truth_csv_path else None
    truth_summary = summarize_truth_frame(truth_frame, factor_names=factor_names) if truth_frame is not None else {}

    frame_path = workspace.frame_path(catalog_key, job_id)
    factor_frame.to_csv(frame_path, index=False, encoding="utf-8")

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
        factor_only_frame = factor_frame[["date", "code", factor_name]].copy()
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
            available_columns=panel.columns.tolist(),
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
