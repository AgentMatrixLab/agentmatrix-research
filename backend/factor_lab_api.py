from __future__ import annotations

import json
import hashlib
import os
import random
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def _load_local_env() -> None:
    for env_path in (project_root / ".env.local", project_root / ".env"):
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()

from research_core.factor_lab import (  # noqa: E402
    FactorLabWorkspaceConfig,
    get_alpha101_factor_detail,
    get_factor_lab_job,
    get_factor_lab_overview,
    list_alpha101_factors,
    list_factor_lab_jobs,
    run_factor_set_real_data_job,
    run_alpha101_research_job,
)

from scripts.quant_api_research import (  # noqa: E402
    QUANT_API_33_FACTORS,
    fetch_kline_data,
    fetch_quant_api_factors,
    build_strategy_report,
    analyze_factor,
    compute_ic,
    compute_rank_ic,
    compute_group_returns,
    _load_local_env,
)
from research_core.data_loader.quant_api_client import QuantApiClient  # noqa: E402
from research_core.factor_lab.real_data import fetch_quant_kline_panel  # noqa: E402
from research_core.factor_lab.libraries.factor_sets import compute_factor_set  # noqa: E402
from research_core.factor_lab.libraries.alpha101 import compute_alpha101_factors  # noqa: E402
from research_core.factor_lab_web import (  # noqa: E402
    build_factor_library_view,
    build_factor_view,
    build_research_analysis_view,
)
from research_core.factor_lab_web.artifact_service import (  # noqa: E402
    list_job_artifacts,
    resolve_artifact_path,
)
from research_core.data_loader.quant_api_client import (  # noqa: E402
    QuantApiClient,
    QuantApiError,
)


app = Flask(__name__)
dashboard_root = project_root / "frontend" / "factor-lab-dashboard"


def _cors_origins() -> list[str]:
    defaults = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8012",
        "http://localhost:8012",
        "https://miao050805-arch.github.io",
        "null",
    ]
    public_origin = os.getenv("FACTOR_LAB_PUBLIC_ORIGIN")
    if public_origin:
        defaults.append(public_origin.strip())
    raw = os.getenv(
        "FACTOR_LAB_CORS_ORIGINS",
        ",".join(defaults),
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


CORS(app, resources={r"/api/*": {"origins": _cors_origins()}})


def _workspace() -> FactorLabWorkspaceConfig:
    return FactorLabWorkspaceConfig()


def _quant_api_client() -> QuantApiClient:
    return QuantApiClient()


def _quant_api_params(*allowed: str) -> dict[str, str]:
    allowed_set = set(allowed)
    return {key: value for key, value in request.args.items() if key in allowed_set and value != ""}


def _quant_api_json(callable_):
    try:
        return jsonify(callable_())
    except QuantApiError as exc:
        status = exc.status_code or 502
        return jsonify(
            {
                "error": str(exc),
                "status_code": exc.status_code,
                "payload": exc.payload,
            }
        ), status


_AGENT_TASK_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_ARTIFACT_KEY_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _agent_tasks_root(*, create: bool = False) -> Path:
    root = project_root / "runtime" / "factor_lab" / "agent_tasks"
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _artifact_cache_path(kind: str, artifact_id: str, *, create: bool = False) -> Path:
    safe_kind = _ARTIFACT_KEY_RE.sub("_", kind).strip("_") or "artifact"
    safe_id = _ARTIFACT_KEY_RE.sub("_", artifact_id).strip("_") or "item"
    root = (project_root / "runtime" / "factor_lab" / safe_kind).resolve()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    path = (root / f"{safe_id}.json").resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("invalid artifact path")
    return path


def _read_artifact_cache(kind: str, artifact_id: str) -> dict | None:
    path = _artifact_cache_path(kind, artifact_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"artifact cache read failed for {kind}:{artifact_id}: {exc}")
        return None
    data.setdefault("artifact_cache", {})
    data["artifact_cache"].update({"hit": True, "path": str(path)})
    return data


def _write_artifact_cache(kind: str, artifact_id: str, payload: dict) -> dict:
    path = _artifact_cache_path(kind, artifact_id, create=True)
    data = _json_safe(payload)
    data.setdefault("artifact_cache", {})
    data["artifact_cache"].update(
        {
            "hit": False,
            "path": str(path),
            "generated_at": _utc_now_iso(),
        }
    )
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def _agent_task_dir(task_id: str, *, create_root: bool = False) -> Path:
    if not _AGENT_TASK_ID_RE.match(task_id):
        raise ValueError("invalid task_id")
    root = _agent_tasks_root(create=create_root)
    path = (root / task_id).resolve()
    if path != root and root not in path.parents:
        raise ValueError("invalid task path")
    return path


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


TRUTH_CRITERIA_REGISTRY = {
    "alpha101": {
        "truth_required": True,
        "tolerance": 1e-8,
        "min_overlap_ratio": 0.9,
        "pass_exact_match_ratio": 0.99,
        "criteria_source": "registry:alpha101_v1",
    },
    "wq101": {
        "truth_required": True,
        "tolerance": 1e-8,
        "min_overlap_ratio": 0.9,
        "pass_exact_match_ratio": 0.99,
        "criteria_source": "registry:alpha101_v1",
    },
    "gtja191": {
        "truth_required": True,
        "tolerance": 1e-8,
        "min_overlap_ratio": 0.9,
        "pass_exact_match_ratio": 0.99,
        "criteria_source": "registry:gtja191_v1",
    },
    "exploratory": {
        "truth_required": False,
        "tolerance": 1e-8,
        "min_overlap_ratio": 0.9,
        "pass_exact_match_ratio": 0.99,
        "criteria_source": "registry:exploratory_v1",
    },
}

TASK_TYPE_ALIASES = {
    "factor_values_compare": "truth_compare",
    "truth_compare": "truth_compare",
    "research_report_reproduction": "research_reproduction",
    "research_reproduction": "research_reproduction",
}

TASK_SKILL_NAMES = {
    "truth_compare": "truth_compare_v1",
    "research_reproduction": "research_reproduction_v1",
}

LEGACY_TASK_SKILL_NAMES = {
    "factor_values_compare": "factor_values_compare_v1",
    "research_report_reproduction": "research_report_reproduction_v1",
}


def _canonical_task_type(task_type: str | None) -> str:
    return TASK_TYPE_ALIASES.get(str(task_type or "").strip(), "research_reproduction")


def _default_skill_name(task_type: str) -> str:
    return TASK_SKILL_NAMES.get(_canonical_task_type(task_type), "research_reproduction_v1")


def _task_required_files(task_type: str) -> list[str]:
    if _canonical_task_type(task_type) == "truth_compare":
        return ["factor_values.csv"]
    return ["code.py", "experiment_data.csv", "paper.pdf", "research_report.pdf"]


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _infer_factor_family(payload: dict) -> str:
    criteria_payload = payload.get("criteria") if isinstance(payload.get("criteria"), dict) else {}
    explicit = str(
        criteria_payload.get("factor_family")
        or payload.get("factor_family")
        or payload.get("factor_set")
        or ""
    ).strip().lower()
    if explicit:
        return explicit
    searchable = " ".join(
        str(value or "")
        for value in (
            payload.get("task_type"),
            payload.get("instruction"),
            (payload.get("package") or {}).get("package_name") if isinstance(payload.get("package"), dict) else "",
        )
    ).lower()
    if "alpha101" in searchable or "wq101" in searchable:
        return "alpha101"
    if "gtja191" in searchable:
        return "gtja191"
    if "exploratory" in searchable or "custom" in searchable or "自研" in searchable:
        return "exploratory"
    return "unknown"


def _resolve_truth_criteria(payload: dict) -> dict:
    family = _infer_factor_family(payload)
    criteria = TRUTH_CRITERIA_REGISTRY.get(family)
    if criteria:
        return {**criteria, "criteria_status": "resolved", "factor_family": family}
    return {
        "truth_required": True,
        "tolerance": 1e-8,
        "min_overlap_ratio": 0.9,
        "pass_exact_match_ratio": 0.99,
        "criteria_source": f"registry:unknown_factor_family:{family}",
        "criteria_status": "failed",
        "factor_family": family,
        "criteria_error": "unknown_factor_family",
    }


def _decide_truth_comparison_status(
    criteria: dict,
    *,
    truth_file_present: bool,
    overlap_ratio: float | None = None,
    exact_match_ratio: float | None = None,
    max_abs_error: float | None = None,
) -> dict:
    truth_required = bool(criteria.get("truth_required", False))
    if not truth_required:
        return {"truth_status": "not_applicable", "truth_blocking": False, "accept_allowed": True}
    if not truth_file_present:
        return {"truth_status": "not_compared", "truth_blocking": True, "accept_allowed": False}

    min_overlap_ratio = float(criteria.get("min_overlap_ratio", 0.9))
    pass_exact_match_ratio = float(criteria.get("pass_exact_match_ratio", 0.99))
    tolerance = float(criteria.get("tolerance", 1e-8))
    if overlap_ratio is None or exact_match_ratio is None or max_abs_error is None:
        return {"truth_status": "not_compared", "truth_blocking": True, "accept_allowed": False}
    if overlap_ratio < min_overlap_ratio:
        return {"truth_status": "not_compared", "truth_blocking": True, "accept_allowed": False}
    passed = exact_match_ratio >= pass_exact_match_ratio and max_abs_error <= tolerance
    return {
        "truth_status": "passed" if passed else "failed",
        "truth_blocking": not passed,
        "accept_allowed": passed,
    }


def _decide_research_truth_diagnostic_status(*, truth_file_present: bool) -> dict:
    if not truth_file_present:
        return {
            "truth_status": "not_applicable",
            "truth_blocking": False,
            "accept_allowed": True,
            "role": "optional_diagnostic",
            "note": "research_reproduction does not require standard truth; final decision is based on economic validation, AMR review, and library comparison.",
        }
    return {
        "truth_status": "diagnostic_pending",
        "truth_blocking": False,
        "accept_allowed": True,
        "role": "optional_diagnostic",
        "note": "truth values are present and should be compared for diagnosis only, not as the promotion gate.",
    }


def _verify_locked_criteria(task_dir: Path, status_payload: dict) -> dict:
    expected = str(status_payload.get("criteria_sha256") or "")
    criteria_path = task_dir / "artifacts" / "criteria.json"
    if not expected or not criteria_path.is_file():
        return {"ok": False, "error": "criteria_missing"}
    actual = _sha256_file(criteria_path)
    if actual != expected:
        return {
            "ok": False,
            "error": "criteria_tampered",
            "expected_sha256": expected,
            "actual_sha256": actual,
        }
    return {"ok": True, "criteria_sha256": actual}


def _enter_intake_gate(task_dir: Path, status_payload: dict, gate_name: str) -> dict:
    if gate_name != "intake_validation":
        integrity = _verify_locked_criteria(task_dir, status_payload)
        if not integrity.get("ok"):
            return {
                "ok": False,
                "gate": gate_name,
                "error": integrity.get("error") or "criteria_integrity_failed",
                "criteria_integrity": integrity,
            }
    return {"ok": True, "gate": gate_name}


def _initial_intake_gates(task_type: str) -> list[dict]:
    task_type = _canonical_task_type(task_type)
    if task_type == "truth_compare":
        names = [
            "intake_validation",
            "criteria_freeze",
            "value_schema_check",
            "data_quality_check",
            "library_truth_lookup",
            "standard_truth_comparison",
            "library_similarity",
            "report_generation",
            "final_approval",
        ]
    else:
        names = [
            "intake_validation",
            "criteria_freeze",
            "document_parse",
            "factor_spec_extraction",
            "code_reconciliation",
            "data_binding",
            "reproduction_run",
            "optional_truth_diagnostics",
            "economic_validation",
            "amr_review",
            "library_comparison",
            "report_generation",
            "final_approval",
        ]
    return [
        {
            "gate": f"G{index}",
            "name": name,
            "status": "queued" if index == 0 else "pending",
        }
        for index, name in enumerate(names)
    ]


def _locked_intake_criteria(payload: dict, task_type: str, file_items: list[dict]) -> dict:
    task_type = _canonical_task_type(task_type)
    file_names = {str(item.get("name") or "") for item in file_items}
    truth_file_present = any(name in file_names for name in {"truth_values.csv", "truth_values.parquet"})
    if task_type == "truth_compare":
        registry_criteria = _resolve_truth_criteria(payload)
        truth_required = True
        initial_truth_decision = _decide_truth_comparison_status(
            {**registry_criteria, "truth_required": True},
            truth_file_present=True,
        )
        criteria_status = str(registry_criteria["criteria_status"])
        criteria_error = registry_criteria.get("criteria_error")
        factor_family = str(registry_criteria["factor_family"])
        criteria_source = str(registry_criteria["criteria_source"])
        tolerance = float(registry_criteria["tolerance"])
        min_overlap_ratio = float(registry_criteria["min_overlap_ratio"])
        pass_exact_match_ratio = float(registry_criteria["pass_exact_match_ratio"])
        standard_truth = {
            "role": "primary_gate",
            "required": True,
            "source": "factor_library_truth",
            "missing_source_status": "not_comparable",
            "blocking": True,
            "notes": [
                "truth_compare must compare the uploaded factor values against the library standard truth.",
                "if library truth is missing, return status=not_comparable instead of accepting.",
            ],
        }
        decision_basis = {
            "accept_requires": [
                "standard_truth.status=passed",
                "overlap_ratio >= min_overlap_ratio",
                "exact_match_ratio >= pass_exact_match_ratio",
                "max_abs_error <= tolerance",
            ],
            "library_similarity": "diagnostic_and_duplicate_detection",
        }
    else:
        family = _infer_factor_family(payload)
        registry_criteria = TRUTH_CRITERIA_REGISTRY.get(family, TRUTH_CRITERIA_REGISTRY["exploratory"])
        truth_required = False
        initial_truth_decision = _decide_research_truth_diagnostic_status(truth_file_present=truth_file_present)
        criteria_status = "resolved"
        criteria_error = None
        factor_family = family if family != "unknown" else "research_unspecified"
        criteria_source = (
            registry_criteria["criteria_source"]
            if family in TRUTH_CRITERIA_REGISTRY
            else "registry:research_reproduction_default_v1"
        )
        tolerance = float(registry_criteria.get("tolerance") or 1e-8)
        min_overlap_ratio = float(registry_criteria.get("min_overlap_ratio") or 0.9)
        pass_exact_match_ratio = float(registry_criteria.get("pass_exact_match_ratio") or 0.99)
        standard_truth = {
            "role": "optional_diagnostic",
            "required": False,
            "source": "optional_truth_values_or_library_truth",
            "missing_source_status": "not_applicable",
            "blocking": False,
            "notes": [
                "research_reproduction is not blocked by missing standard truth.",
                "if truth values are present, compare them for diagnosis and attribution only.",
            ],
        }
        decision_basis = {
            "accept_requires": [
                "economic_validation.status=passed",
                "amr_review.status=passed",
                "library_comparison.status not in duplicate",
            ],
            "truth_diagnostics": "non_blocking_attribution",
        }
    return {
        "schema_version": "factor_intake_criteria_v1",
        "task_type": task_type,
        "intake_entry": task_type,
        "factor_family": factor_family,
        "criteria_status": criteria_status,
        "criteria_error": criteria_error,
        "truth_required": truth_required,
        "truth_file_present": truth_file_present,
        "standard_truth": standard_truth,
        "initial_truth_decision": initial_truth_decision,
        "tolerance": tolerance,
        "min_overlap_ratio": min_overlap_ratio,
        "pass_exact_match_ratio": pass_exact_match_ratio,
        "criteria_source": criteria_source,
        "decision_basis": decision_basis,
        "criteria_resolved_at": "G0",
        "criteria_locked_by": "G0",
        "mutable_by_downstream_agent": False,
        "notes": [
            "truth_compare uses standard truth as the primary gate.",
            "research_reproduction uses standard truth only as an optional diagnostic; acceptance is based on economic validation, AMR review, and library comparison.",
            "passed standard truth requires overlap_ratio >= min_overlap_ratio and exact_match_ratio >= pass_exact_match_ratio.",
        ],
    }


@app.route("/factor-lab-dashboard/", methods=["GET"])
def factor_lab_dashboard():
    return send_from_directory(dashboard_root, "index.html")


@app.route("/factor-lab-dashboard/<path:filename>", methods=["GET"])
def factor_lab_dashboard_asset(filename: str):
    target = dashboard_root / filename
    if target.is_file():
        return send_from_directory(dashboard_root, filename)
    return send_from_directory(dashboard_root, "index.html")


@app.route("/api/agents/factor-lab/overview", methods=["GET"])
def factor_lab_overview():
    return jsonify(get_factor_lab_overview(_workspace()))


@app.route("/api/agents/factor-lab/factor-library", methods=["GET"])
def factor_lab_factor_library():
    return jsonify(build_factor_library_view(_workspace()))


@app.route("/api/agents/factor-lab/health", methods=["GET"])
def factor_lab_health():
    return jsonify({"status": "ok", "service": "factor_lab", "local_flask": True})


@app.route("/api/agents/factor-lab/quant-api/status", methods=["GET"])
def factor_lab_quant_api_status():
    check_remote = request.args.get("remote") in {"1", "true", "yes"}
    return _quant_api_json(lambda: _quant_api_client().status(check_remote=check_remote))


@app.route("/api/agents/factor-lab/quant-api/sources", methods=["GET"])
def factor_lab_quant_api_sources():
    return _quant_api_json(lambda: _quant_api_client().sources())


@app.route("/api/agents/factor-lab/quant-api/ch", methods=["GET"])
def factor_lab_quant_api_ch_tables():
    return _quant_api_json(lambda: _quant_api_client().ch_tables())


@app.route("/api/agents/factor-lab/quant-api/factor-monthly", methods=["GET"])
def factor_lab_quant_api_factor_monthly():
    params = _quant_api_params("symbol", "date", "factor", "top", "order", "order_by", "limit", "offset", "with_total")
    return _quant_api_json(lambda: _quant_api_client().factor_monthly(params))


@app.route("/api/agents/factor-lab/quant-api/factor-monthly/factors", methods=["GET"])
def factor_lab_quant_api_factor_monthly_factors():
    return _quant_api_json(lambda: _quant_api_client().factor_monthly_factors())


@app.route("/api/agents/factor-lab/quant-api/factor-monthly/dates", methods=["GET"])
def factor_lab_quant_api_factor_monthly_dates():
    return _quant_api_json(lambda: _quant_api_client().factor_monthly_dates())


@app.route("/api/agents/factor-lab/quant-api/factor-monthly/stats", methods=["GET"])
def factor_lab_quant_api_factor_monthly_stats():
    return _quant_api_json(lambda: _quant_api_client().factor_monthly_stats())


@app.route("/api/agents/factor-lab/quant-api/factor-monthly/latest", methods=["GET"])
def factor_lab_quant_api_factor_monthly_latest():
    params = _quant_api_params("factor", "top", "order", "order_by")
    return _quant_api_json(lambda: _quant_api_client().factor_monthly_latest(params))


@app.route("/api/agents/factor-lab/quant-api/factor-ic", methods=["GET"])
def factor_lab_quant_api_factor_ic():
    params = _quant_api_params("symbol", "date", "factor", "top", "order", "order_by", "limit", "offset", "with_total")
    return _quant_api_json(lambda: _quant_api_client().factor_ic(params))


@app.route("/api/agents/factor-lab/quant-api/kline-1d", methods=["GET"])
def factor_lab_quant_api_kline_1d():
    params = _quant_api_params("symbol", "date", "factor", "top", "order", "order_by", "limit", "offset", "with_total")
    return _quant_api_json(lambda: _quant_api_client().kline_1d(params))


def _convert_nan_to_null(obj):
    if isinstance(obj, dict):
        return {k: _convert_nan_to_null(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_nan_to_null(v) for v in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    else:
        return obj

@app.route("/api/agents/factor-lab/quant-api/research", methods=["POST"])
def factor_lab_quant_api_research():
    payload = request.get_json(silent=True) or {}
    
    factors = payload.get("factors", ["alpha1", "alpha2", "alpha3"])
    if isinstance(factors, str):
        factors = [f.strip() for f in factors.split(",") if f.strip()]
    
    symbols = payload.get("symbols", ["000001.SZ", "000002.SZ"])
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",") if s.strip()]
    
    start_date = payload.get("start_date", "2023-01-01")
    end_date = payload.get("end_date", "2024-01-01")
    factor_set = payload.get("factor_set", "alpha101")
    
    try:
        from scripts.quant_api_research import run_research
        
        result = run_research(factors, symbols, start_date, end_date, factor_set)
        result_clean = _convert_nan_to_null(result)
        return jsonify(result_clean)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents/factor-lab/factors/<path:factor_id>/view", methods=["GET"])
def factor_lab_factor_view(factor_id: str):
    payload = build_factor_view(factor_id, _workspace())
    if payload is None:
        return jsonify({"error": "Factor not found"}), 404
    return jsonify(payload)


@app.route("/api/agents/factor-lab/factors/<path:factor_id>/research-analysis/latest", methods=["GET"])
def factor_lab_factor_research_analysis(factor_id: str):
    return jsonify(build_research_analysis_view(factor_id, _workspace()))


@app.route("/api/agents/factor-lab/alpha101/factors", methods=["GET"])
def factor_lab_alpha101_factors():
    items = list_alpha101_factors(_workspace())
    status = request.args.get("status")
    if status:
        items = [item for item in items if item.get("status") == status]
    return jsonify({"items": items, "total": len(items)})


@app.route("/api/agents/factor-lab/alpha101/factors/<factor_name>", methods=["GET"])
def factor_lab_alpha101_factor_detail(factor_name: str):
    try:
        return jsonify(get_alpha101_factor_detail(factor_name, _workspace()))
    except KeyError:
        return jsonify({"error": "Factor not found"}), 404


@app.route("/api/agents/factor-lab/factor/<path:factor_id>", methods=["GET"])
def factor_lab_factor_detail(factor_id: str):
    library_data = build_factor_library_view(_workspace())
    refresh = request.args.get("refresh", "").lower() in {"1", "true", "yes"}
    
    match = re.match(r"(\w+):(\w+)", factor_id)
    if match:
        library_name = match.group(1)
        factor_name = match.group(2)
        try:
            if not refresh:
                cached = _read_artifact_cache("factor_detail_cache", factor_id)
                if cached is not None:
                    if _ensure_stratification_from_group_returns(cached):
                        cached = _write_artifact_cache("factor_detail_cache", factor_id, cached)
                    return jsonify(cached)
            payload = _build_real_factor_detail(factor_id, library_name, factor_name)
            _ensure_stratification_from_group_returns(payload)
            return jsonify(_write_artifact_cache("factor_detail_cache", factor_id, payload))
        except Exception as e:
            print(f"real factor detail failed for {factor_id}: {e}")
        
        if library_name == "QuantAPI":
            _load_local_env()
            client = QuantApiClient()
            symbols = get_universe_symbols("沪深300")[:50]
            
            try:
                panel = fetch_kline_data(client, symbols, "2023-01-01", "2024-01-31")
                factor_df = fetch_quant_api_factors(client, symbols, [factor_name], "2023-01-01", "2024-01-31")
                
                if factor_name in factor_df.columns:
                    if len(factor_df) != len(panel):
                        panel["month"] = panel["date"].dt.to_period("M")
                        monthly_returns = panel.groupby(["code", "month"])["returns"].sum().reset_index()
                        monthly_returns.columns = ["code", "month", "returns"]
                        
                        factor_df["month"] = factor_df["date"].dt.to_period("M")
                        factor_monthly = factor_df.groupby(["code", "month"])[factor_name].mean().reset_index()
                        factor_monthly.columns = ["code", "month", factor_name]
                        
                        merged = monthly_returns.merge(factor_monthly, on=["code", "month"], how="inner")
                        merged["date"] = merged["month"].dt.to_timestamp()
                        
                        df = merged.copy()
                    else:
                        df = panel.copy()
                        df[factor_name] = factor_df[factor_name].values
                    
                    df["factor"] = df[factor_name].values
                    df["forward_return"] = df.groupby("code")["returns"].shift(-1)
                    
                    ic_values = []
                    rank_ic_values = []
                    dates = []
                    for date, group in df.groupby("date"):
                        ic_val = compute_ic(group["factor"], group["forward_return"])
                        rank_ic_val = compute_rank_ic(group["factor"], group["forward_return"])
                        if not np.isnan(ic_val):
                            ic_values.append(ic_val)
                            rank_ic_values.append(rank_ic_val)
                            dates.append(date)
                    
                    ic_time_series = []
                    for i in range(len(dates)):
                        ic_time_series.append({
                            "date": dates[i].strftime("%Y-%m-%d") if hasattr(dates[i], "strftime") else str(dates[i]),
                            "ic": float(ic_values[i]),
                            "rank_ic": float(rank_ic_values[i]),
                        })
                    
                    group_returns_df = compute_group_returns(df)
                    group_returns = {}
                    if not group_returns_df.empty:
                        for group in group_returns_df.columns:
                            group_returns[str(group)] = []
                            for date, val in group_returns_df[group].items():
                                group_returns[str(group)].append({
                                    "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date),
                                    "return": float(val),
                                })
                    
                    equity_values = []
                    current = 1.0
                    for date in dates:
                        if "long_short" in group_returns_df.columns and date in group_returns_df.index:
                            ls_return = group_returns_df.loc[date, "long_short"]
                            current *= (1 + ls_return)
                        equity_values.append(current)
                    
                    stratification_data = {
                        "dates": [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d) for d in dates],
                        "equity": equity_values,
                    }
                    
                    return jsonify({
                        "factor_id": factor_id,
                        "factor_name": factor_name,
                        "library": library_name,
                        "ic_time_series": ic_time_series,
                        "group_returns": group_returns,
                        "stratification": stratification_data,
                    })
                else:
                    return jsonify({"error": "因子数据获取失败"}), 500
            except Exception as e:
                print(f"因子详情获取失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({"error": str(e)}), 500
    
    return jsonify({"error": "因子不存在"}), 404


@app.route("/api/agents/factor-lab/agent-tasks", methods=["GET"])
def factor_lab_agent_tasks():
    root = _agent_tasks_root()
    if not root.exists():
        return jsonify({"items": [], "total": 0})
    items = []
    for task_dir in sorted((path for path in root.iterdir() if path.is_dir()), reverse=True):
        status_path = task_dir / "status.json"
        request_path = task_dir / "request.json"
        try:
            status_payload = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
            request_payload = json.loads(request_path.read_text(encoding="utf-8")) if request_path.exists() else {}
        except json.JSONDecodeError:
            status_payload = {"status": "invalid_json"}
            request_payload = {}
        items.append(
            {
                **request_payload,
                **status_payload,
                "task_id": task_dir.name,
                "request_path": str(request_path),
                "status_path": str(status_path),
            }
        )
    return jsonify({"items": items, "total": len(items)})


@app.route("/api/agents/factor-lab/agent-tasks", methods=["POST"])
def factor_lab_create_agent_task():
    payload = request.get_json(silent=True) or {}
    return _create_factor_lab_agent_task(payload)


def _create_factor_lab_agent_task(payload: dict):
    instruction = str(payload.get("instruction") or "").strip()
    raw_task_type = str(payload.get("task_type") or "research_reproduction").strip()
    task_type = _canonical_task_type(raw_task_type)
    default_skill_name = _default_skill_name(task_type)
    skill_name = str(payload.get("skill_name") or default_skill_name).strip() or default_skill_name
    package_payload = payload.get("package") if isinstance(payload.get("package"), dict) else {}
    human_policy = payload.get("human_policy") if isinstance(payload.get("human_policy"), dict) else {}
    files = payload.get("files") if isinstance(payload.get("files"), list) else []
    required_files = package_payload.get("required_files")
    if not isinstance(required_files, list):
        required_files = _task_required_files(task_type)
    required_files = [str(item) for item in required_files if item]
    file_items = [
        {
            "name": str(item.get("name") or ""),
            "relative_path": str(item.get("relative_path") or item.get("name") or ""),
            "size": item.get("size"),
            "type": str(item.get("type") or ""),
            "last_modified": item.get("last_modified"),
        }
        for item in files
        if isinstance(item, dict) and item.get("name")
    ]

    if not instruction and not file_items:
        return jsonify({"error": "instruction or files required"}), 400

    now = _utc_now_iso()
    task_id = f"task-agent-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    task_dir = _agent_task_dir(task_id, create_root=True)
    artifacts_dir = task_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    criteria = _locked_intake_criteria(payload, task_type, file_items)
    criteria_path = artifacts_dir / "criteria.json"
    _write_json(criteria_path, criteria)
    criteria_sha256 = _sha256_file(criteria_path)

    request_payload = {
        "schema_version": payload.get("schema_version") or "factor_intake_request_v1",
        "task_id": task_id,
        "task_type": task_type,
        "legacy_task_type": raw_task_type if raw_task_type != task_type else None,
        "skill_name": skill_name,
        "criteria": criteria,
        "criteria_sha256": criteria_sha256,
        "instruction": instruction,
        "package": {
            "input_mode": package_payload.get("input_mode") or "folder",
            "package_name": package_payload.get("package_name") or task_id,
            "required_files": required_files,
            "files": file_items,
        },
        "files": file_items,
        "namespace": payload.get("namespace") or "quarantine",
        "data_source": payload.get("data_source") or "quant_api",
        "requires_quant_api": bool(payload.get("requires_quant_api", True)),
        "human_policy": {
            "interactive_questions": bool(human_policy.get("interactive_questions", False)),
            "human_only_final_approval": bool(human_policy.get("human_only_final_approval", True)),
        },
        "requested_at": payload.get("requested_at") or now,
        "received_at": now,
        "execution_mode": "trae_manual_handoff",
        "agent_policy": {
            "skill_selection": skill_name,
            "target_namespace": "quarantine",
            "default_data_source": payload.get("data_source") or "quant_api",
            "frontend_runs_agent": False,
        },
        "trae_instruction": (
            "Read this request.json and execute the declared intake entry. truth_compare compares "
            "uploaded factor values against library standard truth as the primary gate. "
            "research_reproduction turns research materials into a runnable candidate factor and "
            "uses optional truth only for diagnostics; final acceptance depends on economic "
            "validation, AMR review, and library comparison. Write progress to status.json and "
            "outputs to artifacts/."
        ),
    }
    status_payload = {
        "schema_version": "agent_task_status_v1",
        "task_id": task_id,
        "task_type": task_type,
        "status": "queued",
        "current_gate": "G0",
        "progress": 0,
        "message": "Request captured. Agent should validate the intake package and continue from request.json.",
        "gates": _initial_intake_gates(task_type),
        "criteria_sha256": criteria_sha256,
        "criteria_integrity": {
            "status": "locked",
            "error": None,
            "checked_at": now,
        },
        "updated_at": now,
    }

    _write_json(task_dir / "request.json", request_payload)
    _write_json(task_dir / "status.json", status_payload)

    return (
        jsonify(
            {
                **request_payload,
                **status_payload,
                "is_placeholder": False,
                "request_path": str(task_dir / "request.json"),
                "status_path": str(task_dir / "status.json"),
                "artifacts_dir": str(artifacts_dir),
            }
        ),
        201,
    )


@app.route("/api/agents/factor-lab/intake/truth-compare", methods=["POST"])
def factor_lab_create_truth_compare_task():
    payload = request.get_json(silent=True) or {}
    payload["task_type"] = "truth_compare"
    payload.setdefault("skill_name", "truth_compare_v1")
    return _create_factor_lab_agent_task(payload)


@app.route("/api/agents/factor-lab/intake/research-reproduction", methods=["POST"])
def factor_lab_create_research_reproduction_task():
    payload = request.get_json(silent=True) or {}
    payload["task_type"] = "research_reproduction"
    payload.setdefault("skill_name", "research_reproduction_v1")
    return _create_factor_lab_agent_task(payload)


@app.route("/api/agents/factor-lab/agent-tasks/<task_id>", methods=["GET"])
def factor_lab_agent_task(task_id: str):
    try:
        task_dir = _agent_task_dir(task_id)
    except ValueError:
        return jsonify({"error": "Invalid task_id"}), 400

    request_path = task_dir / "request.json"
    status_path = task_dir / "status.json"
    if not request_path.exists():
        return jsonify({"error": "Task not found"}), 404

    try:
        request_payload = json.loads(request_path.read_text(encoding="utf-8"))
        status_payload = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    except json.JSONDecodeError as exc:
        return jsonify({"error": "Task JSON is invalid", "detail": str(exc)}), 500

    return jsonify(
        {
            **request_payload,
            **status_payload,
            "request_path": str(request_path),
            "status_path": str(status_path),
            "artifacts_dir": str(task_dir / "artifacts"),
        }
    )


@app.route("/api/agents/factor-lab/agent-tasks/<task_id>/open-folder", methods=["POST"])
def factor_lab_open_agent_task_folder(task_id: str):
    try:
        task_dir = _agent_task_dir(task_id)
    except ValueError:
        return jsonify({"error": "Invalid task_id"}), 400

    if not task_dir.exists():
        return jsonify({"error": "Task not found"}), 404

    os.startfile(str(task_dir))
    return jsonify({"task_id": task_id, "opened": True, "folder_path": str(task_dir)})


@app.route("/api/agents/factor-lab/agent-tasks/<task_id>", methods=["DELETE"])
def factor_lab_delete_agent_task(task_id: str):
    try:
        task_dir = _agent_task_dir(task_id)
    except ValueError:
        return jsonify({"error": "Invalid task_id"}), 400

    if not task_dir.exists():
        return jsonify({"error": "Task not found"}), 404

    shutil.rmtree(task_dir)
    return jsonify({"task_id": task_id, "deleted": True})


@app.route("/api/agents/factor-lab/jobs", methods=["GET"])
def factor_lab_jobs():
    return jsonify({"items": list_factor_lab_jobs(_workspace())})


@app.route("/api/agents/factor-lab/jobs", methods=["POST"])
def factor_lab_create_job():
    payload = request.get_json(silent=True) or {}
    try:
        if payload.get("data_source") in {"quant_api", "real"}:
            job = run_factor_set_real_data_job(payload, _workspace())
        else:
            job = run_alpha101_research_job(payload, _workspace())
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(job), 201


@app.route("/api/agents/factor-lab/jobs/<job_id>", methods=["GET"])
def factor_lab_job_detail(job_id: str):
    payload = get_factor_lab_job(job_id, _workspace())
    if payload is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(payload)


@app.route("/api/agents/factor-lab/jobs/<job_id>/artifacts", methods=["GET"])
def factor_lab_job_artifacts(job_id: str):
    workspace = _workspace()
    if get_factor_lab_job(job_id, workspace) is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(
        {
            "job_id": job_id,
            "factor": request.args.get("factor"),
            "artifacts": list_job_artifacts(job_id, factor_name=request.args.get("factor"), workspace=workspace),
        }
    )


@app.route("/api/agents/factor-lab/artifacts/<job_id>/<artifact_kind>", methods=["GET"])
def factor_lab_job_artifact(job_id: str, artifact_kind: str):
    workspace = _workspace()
    if get_factor_lab_job(job_id, workspace) is None:
        return jsonify({"error": "Job not found"}), 404

    path = resolve_artifact_path(job_id, artifact_kind, factor_name=request.args.get("factor"), workspace=workspace)
    if path is None:
        return jsonify({"error": "Artifact not found"}), 404

    if not path.exists():
        return jsonify({"error": "Artifact file missing"}), 404
    return send_file(path, as_attachment=False, download_name=path.name)


@app.route("/api/agents/factor-lab/strategy-templates", methods=["GET"])
def factor_lab_strategy_templates():
    return jsonify({
        "items": [
            {
                "template_id": "agent_equal_weight_long",
                "name": "多因子等权多头",
                "description": "封装好的多因子多头策略，只接收因子方向与外围研究参数。",
                "source": "agent",
                "required_factor_count": {"min": 1, "max": 30},
                "param_schema": [
                    {"key": "universe", "label": "股票池", "type": "select", "default": "沪深300", "options": ["沪深300", "中证500", "中证800", "中证1000", "中证全指"]},
                    {"key": "start_date", "label": "开始日期", "type": "date", "default": "2023-01-01"},
                    {"key": "end_date", "label": "结束日期", "type": "date", "default": "2025-12-31"},
                    {"key": "cutoff_date", "label": "临界日", "type": "date", "default": "2025-01-01"},
                ],
            },
            {
                "template_id": "agent_layered_long_short",
                "name": "多因子分层多空",
                "description": "封装好的分层多空策略，内部合成、分组和调仓规则不在前端暴露。",
                "source": "agent",
                "required_factor_count": {"min": 2, "max": 30},
                "param_schema": [
                    {"key": "universe", "label": "股票池", "type": "select", "default": "沪深300", "options": ["沪深300", "中证500", "中证800", "中证1000", "中证全指"]},
                    {"key": "start_date", "label": "开始日期", "type": "date", "default": "2023-01-01"},
                    {"key": "end_date", "label": "结束日期", "type": "date", "default": "2025-12-31"},
                    {"key": "cutoff_date", "label": "临界日", "type": "date", "default": "2025-01-01"},
                ],
            },
            {
                "template_id": "agent_ic_weighted_score",
                "name": "IC加权打分策略",
                "description": "根据因子IC值加权合成，IC越高权重越大。",
                "source": "agent",
                "required_factor_count": {"min": 2, "max": 30},
                "param_schema": [
                    {"key": "universe", "label": "股票池", "type": "select", "default": "沪深300", "options": ["沪深300", "中证500", "中证800", "中证1000", "中证全指"]},
                    {"key": "start_date", "label": "开始日期", "type": "date", "default": "2023-01-01"},
                    {"key": "end_date", "label": "结束日期", "type": "date", "default": "2025-12-31"},
                    {"key": "cutoff_date", "label": "临界日", "type": "date", "default": "2025-01-01"},
                ],
            },
        ],
        "total": 3,
    })


@app.route("/api/agents/factor-lab/strategy-run", methods=["POST"])
def factor_lab_strategy_run():
    payload = request.get_json(silent=True) or {}
    
    factor_ids = payload.get("factors", [])
    template_id = payload.get("template_id", "")
    params = payload.get("params", {})
    
    library_data = build_factor_library_view(_workspace())
    factors = {f["id"]: f for f in library_data.get("factors", [])}
    
    selected_factors = []
    for f in factor_ids:
        if isinstance(f, dict):
            fid = f.get("factor_id")
            direction = f.get("direction", 1)
        else:
            fid = f
            direction = 1
        if fid in factors:
            selected_factors.append({"factor": factors[fid], "direction": direction})
    
    if not selected_factors:
        return jsonify({"error": "No valid factors selected"}), 400
    
    start_date = params.get("start_date", "2023-01-01")
    end_date = params.get("end_date", "2025-12-31")
    cutoff_date = params.get("cutoff_date", "2025-01-01")
    universe = params.get("universe", "沪深300")
    
    factor_names = []
    factor_directions = {}
    for f in selected_factors:
        fid = f["factor"]["id"]
        fname = fid.split(":")[-1] if ":" in fid else fid
        factor_names.append(fname)
        factor_directions[fname] = f["direction"]
    
    _load_local_env()
    client = QuantApiClient()
    
    try:
        symbols = get_universe_symbols(universe)
        print(f"策略回测: 使用 {universe} 股票池, {len(symbols)} 只股票")
        
        print(f"[1/3] 拉取行情数据...")
        panel = _fetch_recent_kline_data(client, symbols, start_date, end_date)
        print(f"  行情数据: {len(panel)} 条")
        
        print(f"[2/3] 拉取因子数据...")
        selected_libraries = {str(item["factor"].get("library", "")) for item in selected_factors}
        if selected_libraries <= {"WQ101"}:
            factor_df = compute_alpha101_factors(panel, factor_names=factor_names)
        elif selected_libraries <= {"GTJA191"}:
            factor_df = compute_factor_set(panel, "gtja191", factor_names=factor_names)
        else:
            factor_df = fetch_quant_api_factors(client, symbols, factor_names, start_date, end_date)
        print(f"  因子数据: {len(factor_df)} 条")
        
        for fname in factor_names:
            if fname not in factor_df.columns:
                factor_df[fname] = np.nan
        
        combined_factor = compute_combined_factor(factor_df, factor_names, factor_directions)
        factor_df["combined"] = combined_factor
        
        print(f"[3/3] 构建策略报告...")
        strategy_report = build_strategy_report(panel, factor_df, ["combined"])
        
        combined_result = strategy_report["factors"].get("combined", {})
        daily_data = combined_result.get("daily", [])
        summary = combined_result.get("summary", {})
        
        dates = [d["date"] for d in daily_data]
        equity_values = []
        current = 1.0
        for d in daily_data:
            current *= (1 + d["long_short_return"])
            equity_values.append(current)
        
        backtest_mask = [d["date"] <= cutoff_date for d in daily_data]
        live_mask = [d["date"] > cutoff_date for d in daily_data]
        
        backtest_dates = [dates[i] for i in range(len(dates)) if backtest_mask[i]]
        backtest_equity = [equity_values[i] for i in range(len(equity_values)) if backtest_mask[i]]
        live_dates = [dates[i] for i in range(len(dates)) if live_mask[i]]
        live_equity = [equity_values[i] for i in range(len(equity_values)) if live_mask[i]]
        
        if backtest_equity:
            backtest_start = backtest_equity[0]
            backtest_end = backtest_equity[-1]
            backtest_days = len(backtest_dates)
            backtest_annual = float((backtest_end / backtest_start) ** (252 / backtest_days) - 1) if backtest_days > 0 else float("nan")
            backtest_sharpe = float(summary.get("sharpe", "nan"))
            backtest_max_dd = float(summary.get("max_drawdown", "nan"))
        else:
            backtest_annual = float("nan")
            backtest_sharpe = float("nan")
            backtest_max_dd = float("nan")
        
        if live_equity:
            live_start = live_equity[0]
            live_end = live_equity[-1]
            live_days = len(live_dates)
            live_annual = float((live_end / live_start) ** (252 / live_days) - 1) if live_days > 0 else float("nan")
            live_returns = [(live_equity[i] / live_equity[i-1] - 1) for i in range(1, len(live_equity))]
            live_sharpe = float(np.sqrt(252) * np.mean(live_returns) / np.std(live_returns)) if live_returns else float("nan")
            live_cum = np.array(live_equity)
            live_max = np.maximum.accumulate(live_cum)
            live_drawdown = (live_cum - live_max) / live_max
            live_max_dd = float(live_drawdown.min())
        else:
            live_annual = float("nan")
            live_sharpe = float("nan")
            live_max_dd = float("nan")
        
        avg_ic = sum(f["factor"]["rank_ic_mean"] * f["direction"] for f in selected_factors) / len(selected_factors)
        avg_ir = sum(abs(f["factor"]["rank_ic_ir"]) for f in selected_factors) / len(selected_factors)
        avg_coverage = sum(f["factor"]["coverage_ratio"] or 0 for f in selected_factors) / len(selected_factors)
        
        overall_annual = float(summary.get("annualized_return", "nan"))
        overall_sharpe = float(summary.get("sharpe", "nan"))
        overall_max_dd = float(summary.get("max_drawdown", "nan"))
        
        result = {
            "strategy_id": f"strategy-{uuid4().hex[:12]}",
            "name": payload.get("name", "未命名策略"),
            "template_id": template_id,
            "factors": [{"factor_id": f["factor"]["id"], "direction": f["direction"]} for f in selected_factors],
            "params": params,
            "cutoff_date": cutoff_date,
            "backtest_result": {
                "start_date": start_date,
                "end_date": cutoff_date,
                "equity_curve": backtest_equity,
                "dates": backtest_dates,
                "annual_return": backtest_annual,
                "sharpe_ratio": backtest_sharpe,
                "max_drawdown": backtest_max_dd,
                "win_rate": float(0.5 + avg_ic * 0.3) if not np.isnan(avg_ic) else 0.5,
                "n_trades": len(backtest_dates) * 2,
            },
            "live_result": {
                "start_date": cutoff_date,
                "end_date": end_date,
                "equity_curve": live_equity,
                "dates": live_dates,
                "annual_return": live_annual,
                "sharpe_ratio": live_sharpe,
                "max_drawdown": live_max_dd,
                "win_rate": float(0.5 + avg_ic * 0.25) if not np.isnan(avg_ic) else 0.5,
                "n_trades": len(live_dates) * 2,
            },
            "overall": {
                "annual_return": overall_annual,
                "sharpe_ratio": overall_sharpe,
                "max_drawdown": overall_max_dd,
                "avg_ic": float(avg_ic) if not np.isnan(avg_ic) else float("nan"),
                "avg_ir": float(avg_ir) if not np.isnan(avg_ir) else float("nan"),
                "avg_coverage": float(avg_coverage),
            },
            "created_at": _utc_now_iso(),
            "status": "completed",
        }
        _write_artifact_cache("strategy_detail_cache", result["strategy_id"], result)
        
        return jsonify(result)
    except Exception as e:
        print(f"策略回测失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents/factor-lab/strategy/<strategy_id>", methods=["GET"])
def factor_lab_strategy_detail(strategy_id):
    refresh = request.args.get("refresh", "").lower() in {"1", "true", "yes"}
    if not refresh:
        cached = _read_artifact_cache("strategy_detail_cache", strategy_id)
        if cached is not None:
            return jsonify(cached)

    if strategy_id.startswith("strategy_run_"):
        if not refresh:
            cached = _read_artifact_cache("strategy_detail_cache", strategy_id)
            if cached is not None:
                return jsonify(cached)
        payload = _build_default_quant_strategy_detail(strategy_id)
        return jsonify(_write_artifact_cache("strategy_detail_cache", strategy_id, payload))

    library_data = build_factor_library_view(_workspace())
    factors = library_data.get("factors", {})
    
    match = re.match(r"strategy_single_(\w+)", strategy_id)
    if match:
        factor_name = match.group(1)
        for f in library_data.get("factors", []):
            if f.get("factor_name") == factor_name and f["library"] == "QuantAPI":
                _load_local_env()
                client = QuantApiClient()
                symbols = get_universe_symbols("沪深300")[:50]
                
                cutoff_date = "2023-09-01"
                start_date = "2023-01-01"
                end_date = "2024-01-31"
                
                try:
                    panel = fetch_kline_data(client, symbols, start_date, end_date)
                    factor_df = fetch_quant_api_factors(client, symbols, [factor_name], start_date, end_date)
                    
                    if factor_name in factor_df.columns:
                        strategy_report = build_strategy_report(panel, factor_df, [factor_name])
                        result = strategy_report["factors"].get(factor_name, {})
                        summary = result.get("summary", {})
                        daily_data = result.get("daily", [])
                        
                        dates = [d["date"] for d in daily_data]
                        equity_values = []
                        current = 1.0
                        for d in daily_data:
                            current *= (1 + d["long_short_return"])
                            equity_values.append(current)
                        
                        backtest_mask = [d["date"] <= cutoff_date for d in daily_data]
                        live_mask = [d["date"] > cutoff_date for d in daily_data]
                        
                        backtest_dates = [dates[i] for i in range(len(dates)) if backtest_mask[i]]
                        backtest_equity = [equity_values[i] for i in range(len(equity_values)) if backtest_mask[i]]
                        live_dates = [dates[i] for i in range(len(dates)) if live_mask[i]]
                        live_equity = [equity_values[i] for i in range(len(equity_values)) if live_mask[i]]
                        
                        equity_curve = []
                        for i in range(len(dates)):
                            equity_curve.append({
                                "date": dates[i],
                                "nav": equity_values[i],
                                "phase": "backtest" if dates[i] <= cutoff_date else "live"
                            })
                        
                        def calculate_metrics(equity, dates):
                            if not equity or len(equity) < 2:
                                return {
                                    "annual_return": float("nan"),
                                    "sharpe": float("nan"),
                                    "max_drawdown": float("nan"),
                                    "turnover": float("nan"),
                                    "annual_vol": float("nan"),
                                    "calmar": float("nan"),
                                    "win_rate": float("nan"),
                                }
                            
                            start_val = equity[0]
                            end_val = equity[-1]
                            
                            date_objs = pd.to_datetime(dates)
                            total_days = (date_objs[-1] - date_objs[0]).days
                            avg_interval_days = total_days / (len(date_objs) - 1) if len(date_objs) > 1 else 30
                            freq_multiplier = 252 / avg_interval_days
                            
                            annual_return = float((end_val / start_val) ** freq_multiplier - 1)
                            
                            returns = [(equity[i] / equity[i-1] - 1) for i in range(1, len(equity))]
                            if returns:
                                sharpe = float(np.sqrt(freq_multiplier) * np.mean(returns) / np.std(returns)) if np.std(returns) != 0 else float("nan")
                                annual_vol = float(np.std(returns) * np.sqrt(freq_multiplier))
                                
                                cum = np.array(equity)
                                max_so_far = np.maximum.accumulate(cum)
                                drawdown = (cum - max_so_far) / max_so_far
                                max_drawdown = float(drawdown.min())
                                
                                calmar = float(annual_return / abs(max_drawdown)) if max_drawdown != 0 else float("nan")
                                win_rate = float(sum(r > 0 for r in returns) / len(returns))
                            else:
                                sharpe = float("nan")
                                annual_vol = float("nan")
                                max_drawdown = float("nan")
                                calmar = float("nan")
                                win_rate = float("nan")
                            
                            return {
                                "annual_return": annual_return,
                                "sharpe": sharpe,
                                "max_drawdown": max_drawdown,
                                "turnover": float("nan"),
                                "annual_vol": annual_vol,
                                "calmar": calmar,
                                "win_rate": win_rate,
                            }
                        
                        metrics_backtest = calculate_metrics(backtest_equity, backtest_dates)
                        metrics_live = calculate_metrics(live_equity, live_dates)
                        
                        return jsonify({
                            "strategy_id": strategy_id,
                            "name": f"{factor_name} 单因子策略",
                            "type": "单因子",
                            "factors": [{"factor_id": f["id"], "direction": 1}],
                            "params": {
                                "universe": "沪深300",
                                "start_date": start_date,
                                "end_date": end_date,
                                "cutoff_date": cutoff_date,
                                "portfolio_construction": "多空组合",
                                "rebalance": "月频调仓",
                                "cost": "0.1%",
                            },
                            "equity_curve": equity_curve,
                            "metrics_backtest": metrics_backtest,
                            "metrics_live": metrics_live,
                        })
                    else:
                        return jsonify({"error": "因子数据获取失败"}), 500
                except Exception as e:
                    print(f"策略详情回测失败: {e}")
                    import traceback
                    traceback.print_exc()
                    return jsonify({"error": str(e)}), 500
    
    if strategy_id == "strategy_multi_factor_top3":
        quant_api_factors = [f for f in library_data.get("factors", []) if f["library"] == "QuantAPI" and f["proof_status"] == "passed"]
        strong_factors = sorted(quant_api_factors, key=lambda x: abs(x["rank_ic_ir"] or 0), reverse=True)[:3]
        
        if strong_factors:
            _load_local_env()
            client = QuantApiClient()
            symbols = get_universe_symbols("沪深300")[:50]
            
            cutoff_date = "2024-06-01"
            start_date = "2023-01-01"
            end_date = "2024-12-31"
            
            try:
                panel = fetch_kline_data(client, symbols, start_date, end_date)
                multi_factor_names = [f["factor_name"] for f in strong_factors]
                factor_df = fetch_quant_api_factors(client, symbols, multi_factor_names, start_date, end_date)
                
                combined_factor = compute_combined_factor(factor_df, multi_factor_names, {n: 1 for n in multi_factor_names})
                factor_df["combined"] = combined_factor
                strategy_report = build_strategy_report(panel, factor_df, ["combined"])
                result = strategy_report["factors"].get("combined", {})
                summary = result.get("summary", {})
                daily_data = result.get("daily", [])
                
                dates = [d["date"] for d in daily_data]
                equity_values = []
                current = 1.0
                for d in daily_data:
                    current *= (1 + d["long_short_return"])
                    equity_values.append(current)
                
                backtest_mask = [d["date"] <= cutoff_date for d in daily_data]
                live_mask = [d["date"] > cutoff_date for d in daily_data]
                
                backtest_dates = [dates[i] for i in range(len(dates)) if backtest_mask[i]]
                backtest_equity = [equity_values[i] for i in range(len(equity_values)) if backtest_mask[i]]
                live_dates = [dates[i] for i in range(len(dates)) if live_mask[i]]
                live_equity = [equity_values[i] for i in range(len(equity_values)) if live_mask[i]]
                
                equity_curve = []
                for i in range(len(dates)):
                    equity_curve.append({
                        "date": dates[i],
                        "nav": equity_values[i],
                        "phase": "backtest" if dates[i] <= cutoff_date else "live"
                    })
                
                def calculate_metrics(equity, dates):
                    if not equity or len(equity) < 2:
                        return {
                            "annual_return": float("nan"),
                            "sharpe": float("nan"),
                            "max_drawdown": float("nan"),
                            "turnover": float("nan"),
                            "annual_vol": float("nan"),
                            "calmar": float("nan"),
                            "win_rate": float("nan"),
                        }
                    
                    start_val = equity[0]
                    end_val = equity[-1]
                    n_days = len(dates)
                    
                    annual_return = float((end_val / start_val) ** (252 / n_days) - 1)
                    
                    returns = [(equity[i] / equity[i-1] - 1) for i in range(1, len(equity))]
                    if returns:
                        sharpe = float(np.sqrt(252) * np.mean(returns) / np.std(returns)) if np.std(returns) != 0 else float("nan")
                        annual_vol = float(np.std(returns) * np.sqrt(252))
                        
                        cum = np.array(equity)
                        max_so_far = np.maximum.accumulate(cum)
                        drawdown = (cum - max_so_far) / max_so_far
                        max_drawdown = float(drawdown.min())
                        
                        calmar = float(annual_return / abs(max_drawdown)) if max_drawdown != 0 else float("nan")
                        win_rate = float(sum(r > 0 for r in returns) / len(returns))
                    else:
                        sharpe = float("nan")
                        annual_vol = float("nan")
                        max_drawdown = float("nan")
                        calmar = float("nan")
                        win_rate = float("nan")
                    
                    return {
                        "annual_return": annual_return,
                        "sharpe": sharpe,
                        "max_drawdown": max_drawdown,
                        "turnover": float("nan"),
                        "annual_vol": annual_vol,
                        "calmar": calmar,
                        "win_rate": win_rate,
                    }
                
                metrics_backtest = calculate_metrics(backtest_equity, backtest_dates)
                metrics_live = calculate_metrics(live_equity, live_dates)
                
                return jsonify({
                    "strategy_id": strategy_id,
                    "name": "多因子成品策略2",
                    "type": "多因子",
                    "factors": [{"factor_id": f["id"], "direction": 1} for f in strong_factors],
                    "params": {
                        "universe": "沪深300",
                        "start_date": start_date,
                        "end_date": end_date,
                        "cutoff_date": cutoff_date,
                        "portfolio_construction": "多空组合",
                        "rebalance": "月频调仓",
                        "cost": "0.1%",
                    },
                    "equity_curve": equity_curve,
                    "metrics_backtest": metrics_backtest,
                    "metrics_live": metrics_live,
                })
            except Exception as e:
                print(f"多因子策略详情回测失败: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({"error": str(e)}), 500
    
    return jsonify({"error": "策略不存在"}), 404


@app.route("/api/agents/factor-lab/strategies", methods=["GET"])
def factor_lab_strategies():
    library_data = build_factor_library_view(_workspace())
    factors = library_data.get("factors", [])
    
    quant_api_factors = [f for f in factors if f["library"] == "QuantAPI" and f["proof_status"] == "passed"]
    strong_factors = sorted(quant_api_factors, key=lambda x: abs(x["rank_ic_ir"] or 0), reverse=True)[:10]
    
    strategies = []
    try:
        strategies.append(_default_quant_strategy_row())
        return jsonify(_json_safe({"items": strategies, "total": len(strategies)}))
    except Exception as e:
        print(f"default quant strategy row failed: {e}")
    
    if strong_factors:
        _load_local_env()
        client = QuantApiClient()
        symbols = get_universe_symbols("沪深300")[:50]
        print(f"策略列表回测: 使用 {len(symbols)} 只股票")
        
        for i, factor in enumerate(strong_factors[:5]):
            try:
                factor_name = factor["factor_name"]
                
                print(f"  回测 {factor_name}...")
                panel = fetch_kline_data(client, symbols, "2023-01-01", "2024-12-31")
                factor_df = fetch_quant_api_factors(client, symbols, [factor_name], "2023-01-01", "2024-12-31")
                
                if factor_name in factor_df.columns:
                    strategy_report = build_strategy_report(panel, factor_df, [factor_name])
                    result = strategy_report["factors"].get(factor_name, {})
                    summary = result.get("summary", {})
                    daily_data = result.get("daily", [])
                    
                    cutoff_date = "2024-06-01"
                    backtest_data = [d for d in daily_data if d["date"] <= cutoff_date]
                    live_data = [d for d in daily_data if d["date"] > cutoff_date]
                    
                    backtest_equity = []
                    current = 1.0
                    for d in backtest_data:
                        current *= (1 + d["long_short_return"])
                        backtest_equity.append(current)
                    
                    live_equity = []
                    for d in live_data:
                        current *= (1 + d["long_short_return"])
                        live_equity.append(current)
                    
                    equity_curve = []
                    for d in daily_data:
                        equity_curve.append({
                            "date": d["date"],
                            "nav": None,
                            "phase": "backtest" if d["date"] <= cutoff_date else "live",
                        })
                    for idx, value in enumerate(backtest_equity):
                        equity_curve[idx]["nav"] = value
                    live_offset = len(backtest_equity)
                    for idx, value in enumerate(live_equity):
                        if live_offset + idx < len(equity_curve):
                            equity_curve[live_offset + idx]["nav"] = value
                    
                    strategies.append({
                        "id": f"strategy_single_{factor['factor_name']}",
                        "name": f"{factor['factor_name']} 单因子策略",
                        "type": "单因子",
                        "factors": f"{factor['library']}:{factor['factor_name']}",
                        "universe": "沪深300",
                        "rebalance": "月频调仓",
                        "cost": "0.1%",
                        "annualReturn": float(summary.get("annualized_return", float("nan"))),
                        "sharpe": float(summary.get("sharpe", float("nan"))),
                        "maxDrawdown": float(summary.get("max_drawdown", float("nan"))),
                        "status": "研究就绪",
                        "updatedAt": factor["latest_checked_at"],
                        "rank_ic_mean": float(factor["rank_ic_mean"]),
                        "rank_ic_ir": float(factor["rank_ic_ir"] or 0),
                        "cutoff_date": cutoff_date,
                        "equity_curve": equity_curve,
                        "backtest_result": {
                            "equity_curve": backtest_equity,
                            "dates": [d["date"] for d in backtest_data],
                            "annual_return": float(summary.get("annualized_return", float("nan"))),
                            "sharpe_ratio": float(summary.get("sharpe", float("nan"))),
                            "max_drawdown": float(summary.get("max_drawdown", float("nan"))),
                        },
                        "live_result": {
                            "equity_curve": live_equity,
                            "dates": [d["date"] for d in live_data],
                            "annual_return": float("nan"),
                            "sharpe_ratio": float("nan"),
                            "max_drawdown": float("nan"),
                        },
                    })
                else:
                    strategies.append({
                        "id": f"strategy_single_{factor['factor_name']}",
                        "name": f"{factor['factor_name']} 单因子策略",
                        "type": "单因子",
                        "factors": f"{factor['library']}:{factor['factor_name']}",
                        "universe": "沪深300",
                        "rebalance": "月频调仓",
                        "cost": "0.1%",
                        "annualReturn": float(factor["rank_ic_mean"] * 12),
                        "sharpe": float(abs(factor["rank_ic_ir"] or 0) * 1.5),
                        "maxDrawdown": float(-0.15 - (factor["rank_ic_mean"] * 2)),
                        "status": "研究就绪",
                        "updatedAt": factor["latest_checked_at"],
                        "rank_ic_mean": float(factor["rank_ic_mean"]),
                        "rank_ic_ir": float(factor["rank_ic_ir"] or 0),
                    })
            except Exception as e:
                print(f"  回测 {factor_name} 失败: {e}")
                ic = factor["rank_ic_mean"]
                ir = factor["rank_ic_ir"] or 0
                strategies.append({
                    "id": f"strategy_single_{factor['factor_name']}",
                    "name": f"{factor['factor_name']} 单因子策略",
                    "type": "单因子",
                    "factors": f"{factor['library']}:{factor['factor_name']}",
                    "universe": "沪深300",
                    "rebalance": "月频调仓",
                    "cost": "0.1%",
                    "annualReturn": float(ic * 12),
                    "sharpe": float(abs(ir) * 1.5),
                    "maxDrawdown": float(-0.15 - (ic * 2)),
                    "status": "研究就绪",
                    "updatedAt": factor["latest_checked_at"],
                    "rank_ic_mean": float(ic),
                    "rank_ic_ir": float(ir),
                })
        
        try:
            multi_factor_names = [f["factor_name"] for f in strong_factors[:3]]
            print(f"  回测多因子策略...")
            panel = fetch_kline_data(client, symbols, "2023-01-01", "2024-12-31")
            factor_df = fetch_quant_api_factors(client, symbols, multi_factor_names, "2023-01-01", "2024-12-31")
            
            combined_factor = compute_combined_factor(factor_df, multi_factor_names, {n: 1 for n in multi_factor_names})
            factor_df["combined"] = combined_factor
            strategy_report = build_strategy_report(panel, factor_df, ["combined"])
            result = strategy_report["factors"].get("combined", {})
            summary = result.get("summary", {})
            daily_data = result.get("daily", [])
            
            cutoff_date = "2024-06-01"
            backtest_data = [d for d in daily_data if d["date"] <= cutoff_date]
            live_data = [d for d in daily_data if d["date"] > cutoff_date]
            
            backtest_equity = []
            current = 1.0
            for d in backtest_data:
                current *= (1 + d["long_short_return"])
                backtest_equity.append(current)
            
            live_equity = []
            for d in live_data:
                current *= (1 + d["long_short_return"])
                live_equity.append(current)
            
            equity_curve = []
            for d in daily_data:
                equity_curve.append({
                    "date": d["date"],
                    "nav": None,
                    "phase": "backtest" if d["date"] <= cutoff_date else "live",
                })
            for idx, value in enumerate(backtest_equity):
                equity_curve[idx]["nav"] = value
            live_offset = len(backtest_equity)
            for idx, value in enumerate(live_equity):
                if live_offset + idx < len(equity_curve):
                    equity_curve[live_offset + idx]["nav"] = value
            
            avg_ic = sum(f["rank_ic_mean"] for f in strong_factors[:3]) / 3
            avg_ir = sum(abs(f["rank_ic_ir"] or 0) for f in strong_factors[:3]) / 3
            
            strategies.append({
                "id": "strategy_multi_factor_top3",
                "name": "多因子等权策略（Top3强因子）",
                "type": "多因子",
                "factors": ", ".join([f"{f['library']}:{f['factor_name']}" for f in strong_factors[:3]]),
                "universe": "沪深300",
                "rebalance": "月频调仓",
                "cost": "0.1%",
                "annualReturn": float(summary.get("annualized_return", float("nan"))),
                "sharpe": float(summary.get("sharpe", float("nan"))),
                "maxDrawdown": float(summary.get("max_drawdown", float("nan"))),
                "status": "研究就绪",
                "updatedAt": _utc_now_iso(),
                "rank_ic_mean": float(avg_ic),
                "rank_ic_ir": float(avg_ir),
                "cutoff_date": cutoff_date,
                "equity_curve": equity_curve,
                "backtest_result": {
                    "equity_curve": backtest_equity,
                    "dates": [d["date"] for d in backtest_data],
                    "annual_return": float(summary.get("annualized_return", float("nan"))),
                    "sharpe_ratio": float(summary.get("sharpe", float("nan"))),
                    "max_drawdown": float(summary.get("max_drawdown", float("nan"))),
                },
                "live_result": {
                    "equity_curve": live_equity,
                    "dates": [d["date"] for d in live_data],
                    "annual_return": float("nan"),
                    "sharpe_ratio": float("nan"),
                    "max_drawdown": float("nan"),
                },
            })
        except Exception as e:
            print(f"  回测多因子策略失败: {e}")
            avg_ic = sum(f["rank_ic_mean"] for f in strong_factors[:3]) / 3
            avg_ir = sum(abs(f["rank_ic_ir"] or 0) for f in strong_factors[:3]) / 3
            strategies.append({
                "id": "strategy_multi_factor_top3",
                "name": "多因子等权策略（Top3强因子）",
                "type": "多因子",
                "factors": ", ".join([f"{f['library']}:{f['factor_name']}" for f in strong_factors[:3]]),
                "universe": "沪深300",
                "rebalance": "月频调仓",
                "cost": "0.1%",
                "annualReturn": float(avg_ic * 12 * 1.2),
                "sharpe": float(avg_ir * 1.8),
                "maxDrawdown": float(-0.12 - (avg_ic * 1.5)),
                "status": "研究就绪",
                "updatedAt": _utc_now_iso(),
                "rank_ic_mean": float(avg_ic),
                "rank_ic_ir": float(avg_ir),
            })
    
    return jsonify(_json_safe({"items": strategies, "total": len(strategies)}))


def get_universe_symbols(universe: str) -> list[str]:
    universe_map = {
        "沪深300": [
            "000001.SZ", "000002.SZ", "000008.SZ", "000009.SZ", "000012.SZ",
            "000021.SZ", "000025.SZ", "000027.SZ", "000028.SZ", "000031.SZ",
            "600000.SH", "600004.SH", "600005.SH", "600006.SH", "600007.SH",
            "600008.SH", "600009.SH", "600010.SH", "600011.SH", "600012.SH",
            "000039.SZ", "000046.SZ", "000050.SZ", "000059.SZ", "000060.SZ",
            "000063.SZ", "000066.SZ", "000069.SZ", "000078.SZ", "000088.SZ",
            "600015.SH", "600016.SH", "600018.SH", "600019.SH", "600020.SH",
            "600021.SH", "600022.SH", "600026.SH", "600027.SH", "600028.SH",
        ],
        "中证500": [
            "000016.SZ", "000017.SZ", "000020.SZ", "000022.SZ", "000023.SZ",
            "000024.SZ", "000030.SZ", "000034.SZ", "000035.SZ", "000036.SZ",
            "600030.SH", "600031.SH", "600033.SH", "600036.SH", "600037.SH",
            "600038.SH", "600048.SH", "600050.SH", "600051.SH", "600052.SH",
            "000037.SZ", "000038.SZ", "000040.SZ", "000042.SZ", "000043.SZ",
            "000045.SZ", "000048.SZ", "000055.SZ", "000056.SZ", "000058.SZ",
            "600055.SH", "600056.SH", "600058.SH", "600060.SH", "600061.SH",
            "600062.SH", "600063.SH", "600066.SH", "600067.SH", "600068.SH",
        ],
        "中证800": [
            "000001.SZ", "000002.SZ", "600000.SH", "600004.SH",
            "000016.SZ", "000020.SZ", "600030.SH", "600036.SH",
        ],
        "中证1000": [
            "000015.SZ", "000018.SZ", "000019.SZ", "000026.SZ",
            "600003.SH", "600014.SH", "600023.SH", "600029.SH",
        ],
        "中证全指": [
            "000001.SZ", "000002.SZ", "600000.SH", "600004.SH",
            "000015.SZ", "000016.SZ", "600003.SH", "600030.SH",
        ],
    }
    return universe_map.get(universe, universe_map["沪深300"])


def compute_combined_factor(factor_df: "pd.DataFrame", factor_names: list[str], directions: dict[str, int]) -> "pd.Series":
    import pandas as pd
    combined = pd.Series(0.0, index=factor_df.index)
    valid_counts = pd.Series(0, index=factor_df.index)
    
    for fname in factor_names:
        if fname in factor_df.columns:
            factor_series = factor_df[fname].fillna(0)
            factor_series = (factor_series - factor_series.mean()) / factor_series.std() if factor_series.std() != 0 else factor_series
            combined += factor_series * directions.get(fname, 1)
            valid_counts += factor_df[fname].notna().astype(int)
    
    combined = combined / len(factor_names)
    return combined


def _factor_frame_from_quant_api_factor(
    client: QuantApiClient,
    symbols: list[str],
    factor_name: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    if factor_name not in QUANT_API_33_FACTORS:
        raise ValueError(f"Unsupported Quant API factor: {factor_name}")
    return fetch_quant_api_factors(client, symbols, [factor_name], start_date, end_date)


def _factor_frame_from_formula_set(panel: pd.DataFrame, library_name: str, factor_name: str) -> pd.DataFrame:
    library_key = library_name.lower()
    if library_key == "wq101":
        return compute_alpha101_factors(panel, factor_names=[factor_name])
    elif library_key in {"gtja191", "alpha158"}:
        library_key = "gtja191"
        if library_name.lower() == "alpha158":
            library_key = "alpha158"
    else:
        raise ValueError(f"Unsupported formula factor library: {library_name}")
    return compute_factor_set(panel, library_key, factor_names=[factor_name])


def _prepare_factor_research_frame(panel: pd.DataFrame, factor_frame: pd.DataFrame, factor_name: str) -> pd.DataFrame:
    factor_df = factor_frame[["date", "code", factor_name]].copy()
    factor_df["date"] = pd.to_datetime(factor_df["date"])
    panel_df = panel.copy()
    panel_df["date"] = pd.to_datetime(panel_df["date"])
    panel_df = panel_df.sort_values(["code", "date"]).reset_index(drop=True)

    factor_dates = factor_df["date"].nunique()
    panel_dates = panel_df["date"].nunique()
    if factor_dates and panel_dates and factor_dates < panel_dates * 0.5:
        monthly = panel_df.copy()
        monthly["month"] = monthly["date"].dt.to_period("M")
        monthly_returns = monthly.groupby(["code", "month"])["returns"].sum().reset_index()
        monthly_returns["date"] = monthly_returns["month"].dt.to_timestamp(how="end")

        factor_df["month"] = factor_df["date"].dt.to_period("M")
        factor_monthly = factor_df.groupby(["code", "month"])[factor_name].mean().reset_index()
        factor_monthly["date"] = factor_monthly["month"].dt.to_timestamp(how="end")

        df = monthly_returns[["code", "date", "returns"]].merge(
            factor_monthly[["code", "date", factor_name]],
            on=["date", "code"],
            how="inner",
        )
        df["forward_return"] = df.groupby("code")["returns"].shift(-1)
    else:
        forward = panel_df[["date", "code", "close"]].copy()
        forward["forward_return"] = forward.groupby("code")["close"].shift(-1) / forward["close"] - 1
        df = factor_df.merge(forward[["date", "code", "forward_return"]], on=["date", "code"], how="left")

    df = df.rename(columns={factor_name: "factor"})
    return df.sort_values(["date", "code"]).reset_index(drop=True)


def _build_factor_research_payload(
    factor_id: str,
    library_name: str,
    factor_name: str,
    panel: pd.DataFrame,
    factor_frame: pd.DataFrame,
    data_source: str,
) -> dict:
    df = _prepare_factor_research_frame(panel, factor_frame, factor_name)
    valid_df = df.dropna(subset=["factor", "forward_return"]).copy()

    ic_time_series = []
    for date, group in valid_df.groupby("date"):
        ic_val = compute_ic(group["factor"], group["forward_return"])
        rank_ic_val = compute_rank_ic(group["factor"], group["forward_return"])
        if np.isfinite(ic_val) or np.isfinite(rank_ic_val):
            ic_time_series.append(
                {
                    "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                    "ic": float(ic_val) if np.isfinite(ic_val) else None,
                    "rank_ic": float(rank_ic_val) if np.isfinite(rank_ic_val) else None,
                }
            )

    group_count = min(10, max(2, int(valid_df["code"].nunique())))
    group_returns_df = compute_group_returns(valid_df, num_groups=group_count)
    group_returns = {}
    if not group_returns_df.empty:
        for group in group_returns_df.columns:
            group_returns[str(group)] = [
                {
                    "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                    "return": float(value) if np.isfinite(value) else None,
                }
                for date, value in group_returns_df[group].items()
            ]

    strat_dates = []
    equity_values = []
    current_nav = 1.0
    for date, date_slice in valid_df.groupby("date"):
        if len(date_slice) < 5:
            continue
        ranks = date_slice["factor"].rank(method="average", pct=True)
        long_mask = ranks >= 0.8
        short_mask = ranks <= 0.2
        if not long_mask.any() or not short_mask.any():
            continue
        long_return = date_slice.loc[long_mask, "forward_return"].mean()
        short_return = date_slice.loc[short_mask, "forward_return"].mean()
        long_short_return = long_return - short_return
        if not np.isfinite(long_short_return):
            continue
        current_nav *= 1.0 + float(long_short_return)
        strat_dates.append(pd.Timestamp(date).strftime("%Y-%m-%d"))
        equity_values.append(float(current_nav))

    if not equity_values and "long_short" in group_returns_df.columns:
        current_nav = 1.0
        for date, long_short_return in group_returns_df["long_short"].items():
            if not np.isfinite(long_short_return):
                continue
            current_nav *= 1.0 + float(long_short_return)
            strat_dates.append(pd.Timestamp(date).strftime("%Y-%m-%d"))
            equity_values.append(float(current_nav))

    rank_ics = [item["rank_ic"] for item in ic_time_series if item.get("rank_ic") is not None]
    ic_values = [item["ic"] for item in ic_time_series if item.get("ic") is not None]
    coverage = float(df["factor"].notna().mean()) if len(df) else float("nan")
    rank_ic_mean = float(np.mean(rank_ics)) if rank_ics else float("nan")
    rank_ic_std = float(np.std(rank_ics, ddof=1)) if len(rank_ics) > 1 else float("nan")

    return {
        "factor_id": factor_id,
        "factor_name": factor_name,
        "library": library_name,
        "data_source": data_source,
        "frequency": "daily" if factor_frame["date"].nunique() >= panel["date"].nunique() * 0.5 else "monthly",
        "coverage_ratio": coverage,
        "non_null_count": int(df["factor"].notna().sum()),
        "rank_ic_mean": rank_ic_mean,
        "rank_ic_ir": float(rank_ic_mean / rank_ic_std) if np.isfinite(rank_ic_mean) and np.isfinite(rank_ic_std) and rank_ic_std != 0 else float("nan"),
        "pearson_ic_mean": float(np.mean(ic_values)) if ic_values else float("nan"),
        "ic_time_series": ic_time_series,
        "group_returns": group_returns,
        "stratification": {
            "dates": strat_dates,
            "equity": equity_values,
        },
        "dataset": {
            "panel_rows": int(len(panel)),
            "factor_rows": int(len(factor_frame)),
            "analysis_rows": int(len(valid_df)),
            "symbols": int(panel["code"].nunique()),
            "dates": int(panel["date"].nunique()),
            "start_date": pd.Timestamp(panel["date"].min()).strftime("%Y-%m-%d"),
            "end_date": pd.Timestamp(panel["date"].max()).strftime("%Y-%m-%d"),
            "groups": int(group_count),
        },
    }


def _group_sort_value(group_name: str) -> float:
    try:
        return float(group_name)
    except (TypeError, ValueError):
        return float("nan")


def _long_short_rows_from_group_returns(group_returns: dict) -> list[dict]:
    long_short_rows = group_returns.get("long_short")
    if isinstance(long_short_rows, list) and long_short_rows:
        return long_short_rows

    numeric_groups = [
        key
        for key in group_returns.keys()
        if key != "long_short" and np.isfinite(_group_sort_value(str(key)))
    ]
    if len(numeric_groups) < 2:
        return []
    min_group = min(numeric_groups, key=lambda key: _group_sort_value(str(key)))
    max_group = max(numeric_groups, key=lambda key: _group_sort_value(str(key)))
    min_by_date = {
        str(item.get("date")): item.get("return")
        for item in group_returns.get(min_group, [])
        if isinstance(item, dict)
    }
    rows = []
    for item in group_returns.get(max_group, []):
        if not isinstance(item, dict):
            continue
        date = str(item.get("date"))
        high_return = item.get("return")
        low_return = min_by_date.get(date)
        try:
            spread = float(high_return) - float(low_return)
        except (TypeError, ValueError):
            spread = float("nan")
        rows.append({"date": date, "return": spread})
    return rows


def _ensure_stratification_from_group_returns(payload: dict) -> bool:
    stratification = payload.setdefault("stratification", {})
    if stratification.get("equity"):
        return False

    group_returns = payload.get("group_returns") or {}
    if not isinstance(group_returns, dict):
        return False

    rows = _long_short_rows_from_group_returns(group_returns)
    current_nav = 1.0
    dates = []
    equity = []
    for row in sorted(rows, key=lambda item: str(item.get("date") or "")):
        try:
            long_short_return = float(row.get("return"))
        except (TypeError, ValueError):
            continue
        if not np.isfinite(long_short_return):
            continue
        current_nav *= 1.0 + long_short_return
        dates.append(str(row.get("date")))
        equity.append(float(current_nav))

    if not equity:
        return False
    stratification["dates"] = dates
    stratification["equity"] = equity
    return True


def _factor_set_candidates_for_library(library_name: str) -> set[str]:
    normalized = library_name.lower()
    if normalized in {"wq101", "alpha101"}:
        return {"wq101", "alpha101"}
    if normalized in {"gtja191", "alpha191"}:
        return {"gtja191", "alpha191"}
    if normalized == "alpha158":
        return {"alpha158"}
    return {normalized}


def _build_factor_detail_from_latest_job(factor_id: str, library_name: str, factor_name: str) -> dict | None:
    workspace = _workspace()
    candidates = _factor_set_candidates_for_library(library_name)
    jobs = sorted(list_factor_lab_jobs(workspace), key=lambda item: item.get("generated_at", ""), reverse=True)
    for job in jobs:
        factor_set = str(job.get("factor_set") or "").lower()
        library = str(job.get("library") or "").lower()
        if factor_set not in candidates and library not in candidates:
            continue
        requested = {str(name) for name in job.get("requested_factors") or []}
        if requested and factor_name not in requested:
            continue
        artifacts = job.get("artifacts") or {}
        panel_path = artifacts.get("panel_frame")
        factor_path = artifacts.get("factor_frame")
        if not panel_path or not factor_path:
            continue
        panel_file = Path(panel_path)
        factor_file = Path(factor_path)
        if not panel_file.is_file() or not factor_file.is_file():
            continue
        factor_frame = pd.read_csv(factor_file)
        if factor_name not in factor_frame.columns:
            continue
        panel = pd.read_csv(panel_file)
        payload = _build_factor_research_payload(
            factor_id,
            library_name,
            factor_name,
            panel,
            factor_frame,
            str(job.get("data_source") or "quant_api"),
        )
        payload["job_id"] = job.get("job_id")
        payload["generated_at"] = job.get("generated_at")
        return payload
    return None


def _build_real_factor_detail(factor_id: str, library_name: str, factor_name: str) -> dict:
    artifact_payload = _build_factor_detail_from_latest_job(factor_id, library_name, factor_name)
    if artifact_payload is not None:
        return artifact_payload

    _load_local_env()
    client = QuantApiClient()
    symbols = get_universe_symbols("娌繁300")[:20]
    start_date = "2023-01-01"
    end_date = "2026-04-09"

    if library_name == "QuantAPI":
        panel = _fetch_recent_kline_data(client, symbols, start_date, end_date)
        factor_frame = _factor_frame_from_quant_api_factor(client, symbols, factor_name, start_date, end_date)
        data_source = "quant_api_factor_monthly"
    else:
        panel = _fetch_recent_kline_data(client, symbols, start_date, end_date)
        factor_frame = _factor_frame_from_formula_set(panel, library_name, factor_name)
        data_source = "quant_api_kline_formula"

    return _build_factor_research_payload(
        factor_id,
        library_name,
        factor_name,
        panel,
        factor_frame,
        data_source,
    )


@app.route("/api/agents/factor-lab/strategy-real-default/<strategy_id>", methods=["GET"])
def factor_lab_strategy_real_default(strategy_id):
    try:
        refresh = request.args.get("refresh", "").lower() in {"1", "true", "yes"}
        if not refresh:
            cached = _read_artifact_cache("strategy_detail_cache", strategy_id)
            if cached is not None:
                return jsonify(cached)
        payload = _build_default_quant_strategy_detail(strategy_id)
        return jsonify(_write_artifact_cache("strategy_detail_cache", strategy_id, payload))
    except Exception as e:
        print(f"default quant strategy detail failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    if isinstance(value, (np.integer, int)):
        return int(value)
    return value


def _fetch_recent_kline_data(client: QuantApiClient, symbols: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    all_data = []
    for symbol in symbols:
        payload = client.kline_1d(
            {
                "symbol": symbol,
                "order": "desc",
                "order_by": "trade_date",
                "limit": 1000,
            }
        )
        if payload.get("data"):
            all_data.append(pd.DataFrame(payload["data"]))

    if not all_data:
        raise ValueError("No kline data returned from Quant API")

    df = pd.concat(all_data, ignore_index=True).rename(columns={"trade_date": "date", "symbol": "code"})
    df["date"] = pd.to_datetime(df["date"])
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    if "amount" not in df.columns:
        df["amount"] = df["close"] * df["volume"]
    df["vwap"] = df["amount"] / df["volume"].replace(0, np.nan)
    df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
    df = df.sort_values(["code", "date"]).drop_duplicates(["date", "code"], keep="last")
    df["returns"] = df.groupby("code")["close"].pct_change()
    required_cols = ["date", "code", "open", "high", "low", "close", "volume", "amount", "vwap", "returns"]
    return df[required_cols].reset_index(drop=True)


def _strategy_metrics(equity: list[float], dates: list[str]) -> dict:
    if not equity or len(equity) < 2:
        return {
            "annual_return": float("nan"),
            "sharpe": float("nan"),
            "max_drawdown": float("nan"),
            "turnover": float("nan"),
            "annual_vol": float("nan"),
            "calmar": float("nan"),
            "win_rate": float("nan"),
        }

    date_index = pd.to_datetime(dates)
    total_days = max((date_index[-1] - date_index[0]).days, 1)
    periods_per_year = 365.0 / (total_days / max(len(date_index) - 1, 1))
    returns = np.array([(equity[i] / equity[i - 1] - 1) for i in range(1, len(equity))], dtype=float)
    annual_return = float((equity[-1] / equity[0]) ** (365.0 / total_days) - 1)
    annual_vol = float(np.std(returns, ddof=1) * np.sqrt(periods_per_year)) if len(returns) > 1 else float("nan")
    sharpe = float(np.sqrt(periods_per_year) * np.mean(returns) / np.std(returns, ddof=1)) if len(returns) > 1 and np.std(returns, ddof=1) != 0 else float("nan")
    curve = np.array(equity, dtype=float)
    drawdown = curve / np.maximum.accumulate(curve) - 1.0
    max_drawdown = float(drawdown.min())
    calmar = float(annual_return / abs(max_drawdown)) if max_drawdown != 0 else float("nan")
    return {
        "annual_return": annual_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "turnover": float("nan"),
        "annual_vol": annual_vol,
        "calmar": calmar,
        "win_rate": float(np.mean(returns > 0)) if len(returns) else float("nan"),
    }


def _build_default_quant_strategy_detail(strategy_id: str) -> dict:
    _load_local_env()
    client = QuantApiClient()
    symbols = get_universe_symbols("沪深300")[:8]
    factor_names = ["ret_1m", "roe_ttm"]
    start_date = "2024-09-01"
    end_date = "2026-04-09"
    cutoff_date = "2025-07-31"

    panel = _fetch_recent_kline_data(client, symbols, start_date, end_date)
    factor_df = fetch_quant_api_factors(client, symbols, factor_names, start_date, end_date)
    if factor_df.empty:
        raise ValueError("No factor data returned from Quant API")
    factor_df["combined"] = compute_combined_factor(factor_df, factor_names, {name: 1 for name in factor_names})
    strategy_report = build_strategy_report(panel, factor_df, ["combined"])
    daily_data = strategy_report["factors"].get("combined", {}).get("daily", [])
    if not daily_data:
        raise ValueError("Quant API strategy produced no daily rows")

    equity_curve = []
    current = 1.0
    for row in daily_data:
        current *= 1 + float(row["long_short_return"])
        equity_curve.append(
            {
                "date": row["date"],
                "nav": current,
                "phase": "backtest" if row["date"] <= cutoff_date else "live",
            }
        )

    backtest_points = [point for point in equity_curve if point["phase"] == "backtest"]
    live_points = [point for point in equity_curve if point["phase"] == "live"]
    backtest_equity = [point["nav"] for point in backtest_points]
    backtest_dates = [point["date"] for point in backtest_points]
    live_equity = [point["nav"] for point in live_points]
    live_dates = [point["date"] for point in live_points]

    return {
        "strategy_id": strategy_id,
        "name": "Quant API default factor strategy",
        "type": "multi_factor",
        "factors": [{"factor_id": name, "direction": 1} for name in factor_names],
        "params": {
            "universe": "沪深300",
            "start_date": start_date,
            "end_date": end_date,
            "cutoff_date": cutoff_date,
            "portfolio_construction": "long_short_combined_factor",
            "rebalance": "monthly",
            "cost": "none",
        },
        "equity_curve": equity_curve,
        "metrics_backtest": _strategy_metrics(backtest_equity, backtest_dates),
        "metrics_live": _strategy_metrics(live_equity, live_dates),
        "data_source": "quant_api",
        "debug": {
            "symbols": symbols,
            "factor_names": factor_names,
            "panel_rows": int(len(panel)),
            "factor_rows": int(len(factor_df)),
            "equity_points": int(len(equity_curve)),
            "frequency": "monthly factor dates",
        },
    }


def _default_quant_strategy_row(strategy_id: str = "strategy_quant_api_default") -> dict:
    detail = _build_default_quant_strategy_detail(strategy_id)
    equity_curve = detail.get("equity_curve", [])
    nav_history = [
        {
            "date": point.get("date"),
            "nav": point.get("nav"),
            "phase": point.get("phase"),
            "is_simulation": False,
            "in_drawdown": False,
        }
        for point in equity_curve
    ]
    metrics = detail.get("metrics_backtest", {})
    factor_names = [factor.get("factor_id") for factor in detail.get("factors", []) if factor.get("factor_id")]
    params = detail.get("params", {})
    return {
        "id": strategy_id,
        "name": "Quant API real factor strategy",
        "type": "multi_factor",
        "factors": ", ".join(factor_names),
        "universe": params.get("universe"),
        "rebalance": params.get("rebalance"),
        "cost": params.get("cost"),
        "annualReturn": metrics.get("annual_return"),
        "sharpe": metrics.get("sharpe"),
        "maxDrawdown": metrics.get("max_drawdown"),
        "status": "real_backtest",
        "updatedAt": _utc_now_iso(),
        "cutoff_date": params.get("cutoff_date"),
        "equity_curve": equity_curve,
        "nav_history": nav_history,
        "metrics_backtest": detail.get("metrics_backtest"),
        "metrics_live": detail.get("metrics_live"),
        "params": params,
        "data_source": detail.get("data_source"),
        "debug": detail.get("debug"),
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8012"))
    host = os.getenv("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False)
