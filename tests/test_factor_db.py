"""factor_db 元数据与 API 回归测试。

覆盖：目录统计（含 qlib-factor-zoo 来源）、检索、详情、字典、
Flask 端点（含 zoo 因子值未就绪时的 425 语义）。
"""

from __future__ import annotations

import json

import pytest

flask = pytest.importorskip("flask")

import backend.factor_lab_api as factor_lab_api  # noqa: E402
from research_core.factor_db.api import create_app  # noqa: E402
from research_core.factor_db.metadata import (  # noqa: E402
    dictionary_rows,
    get_factor,
    get_stats,
    list_factors,
)

EXPECTED_SOURCES = {
    "QAPI33": 33,
    "ALPHA101": 101,
    "GTJA191": 191,
    "TDXGS": 88,
    "JQ110": 109,
    "ALPHA158": 158,
    "ALPHA360": 360,
    "BARRA": 11,
    "JQGM": 7,
}
CONTROLLED_API_KEY = "test-factor-db-key"


@pytest.fixture(scope="module")
def client():
    app = create_app()
    return app.test_client()


@pytest.fixture(scope="module")
def backend_client():
    return factor_lab_api.app.test_client()


# ---------------------------------------------------------------------------
# 元数据层
# ---------------------------------------------------------------------------
def test_stats_include_zoo_sources():
    stats = get_stats()
    assert stats["by_source"] == EXPECTED_SOURCES
    assert stats["total_factors"] == sum(EXPECTED_SOURCES.values())


def test_get_factor_by_full_id():
    row = get_factor("GTJA191:GTJA001")
    assert row is not None
    assert row["name_cn"].startswith("国泰君安191")
    assert row["formula_latex"]  # LaTeX 转换非空


def test_get_factor_by_short_name():
    assert get_factor("GTJA001")["factor_id"] == "GTJA191:GTJA001"
    assert get_factor("TDXGS_EMA_05")["factor_id"] == "TDXGS:TDXGS_EMA_05"
    assert get_factor("JQ110_beta")["factor_id"] == "JQ110:JQ110_beta"


def test_list_factors_by_source():
    for source, count in EXPECTED_SOURCES.items():
        rows, total = list_factors(source=source)
        assert total == count, source
        assert len(rows) == count
        assert all(r["factor_id"].startswith(f"{source}:") for r in rows)


def test_search_chinese():
    rows, total = list_factors(search="布林带")
    assert total >= 2
    assert any(r["factor_id"] == "JQ110:JQ110_boll_up" for r in rows)


def test_dictionary_rows_cover_all():
    assert len(dictionary_rows()) == sum(EXPECTED_SOURCES.values())


# ---------------------------------------------------------------------------
# API 层
# ---------------------------------------------------------------------------
def test_api_stats(client):
    r = client.get("/api/factor-db/stats")
    assert r.status_code == 200
    assert r.json["total_factors"] == sum(EXPECTED_SOURCES.values())


def test_api_factors_filter(client):
    r = client.get("/api/factor-db/factors?source=TDXGS&limit=5")
    assert r.status_code == 200
    assert r.json["total"] == 88
    assert len(r.json["factors"]) == 5


def test_api_factor_detail(client):
    r = client.get("/api/factor-db/factors/ALPHA158:KMID")
    assert r.status_code == 200
    assert r.json["name_cn"] == "K线实体幅度（KMID）"


def test_public_metadata_stays_open_when_auth_enabled(client, monkeypatch):
    monkeypatch.setenv("FACTOR_DB_API_KEYS", CONTROLLED_API_KEY)
    r = client.get("/api/factor-db/stats")
    assert r.status_code == 200
    assert r.json["total_factors"] == sum(EXPECTED_SOURCES.values())


def test_api_controlled_values_require_api_key(client, monkeypatch):
    monkeypatch.setenv("FACTOR_DB_API_KEYS", CONTROLLED_API_KEY)
    r = client.get("/api/factor-db/factors/JQ110:JQ110_beta/values")
    assert r.status_code == 401
    assert "API Key" in r.json["error"]


def test_api_zoo_factor_values_not_ready(client, monkeypatch):
    """zoo 来源因子值未生成时返回 425（早期数据不可用语义）。"""
    monkeypatch.setenv("FACTOR_DB_API_KEYS", CONTROLLED_API_KEY)
    r = client.get(
        "/api/factor-db/factors/JQ110:JQ110_beta/values",
        headers={"X-FactorDB-API-Key": CONTROLLED_API_KEY},
    )
    assert r.status_code == 425
    assert "qlib" in r.json["error"]


def test_api_distribution_demo(client):
    r = client.get("/api/factor-db/factors/GTJA191:GTJA001/distribution?demo=1")
    assert r.status_code == 200
    assert r.json["demo"] is True


def test_api_meta_export_stays_public(client, monkeypatch):
    monkeypatch.setenv("FACTOR_DB_API_KEYS", CONTROLLED_API_KEY)
    r = client.get("/api/factor-db/factors/QAPI33:roe_ttm/export?scope=meta&format=csv")
    assert r.status_code == 200
    assert "text/csv" in r.content_type


def test_api_dictionary(client):
    r = client.get("/api/factor-db/dictionary")
    assert r.status_code == 200
    assert r.json["count"] == sum(EXPECTED_SOURCES.values())


def test_api_quant_status_public_view(client, monkeypatch):
    monkeypatch.setenv("FACTOR_DB_API_KEYS", CONTROLLED_API_KEY)
    r = client.get("/api/factor-db/quant-api/status")
    assert r.status_code == 200
    assert r.json["auth_required"] is True
    assert r.json["mode"] == "api_key_list"
    assert "base_url" not in r.json


def test_customer_policy_expires_access(client, monkeypatch):
    monkeypatch.setenv(
        "FACTOR_DB_CUSTOMER_POLICIES_JSON",
        json.dumps(
            [
                {
                    "customer_id": "expired-client",
                    "name": "Expired Client",
                    "api_key": "expired-key",
                    "expires_at": "2020-01-01T00:00:00Z",
                    "allowed_sources": ["QAPI33"],
                    "allow_export_values": True,
                }
            ],
            ensure_ascii=False,
        ),
    )
    r = client.get("/api/factor-db/factors/QAPI33:roe_ttm/values", headers={"X-FactorDB-API-Key": "expired-key"})
    assert r.status_code == 403
    assert "过期" in r.json["error"]


def test_customer_policy_restricts_factor_scope(client, monkeypatch):
    monkeypatch.setenv(
        "FACTOR_DB_CUSTOMER_POLICIES_JSON",
        json.dumps(
            [
                {
                    "customer_id": "scoped-client",
                    "name": "Scoped Client",
                    "api_key": "scoped-key",
                    "allowed_sources": ["QAPI33"],
                    "allow_export_values": True,
                }
            ],
            ensure_ascii=False,
        ),
    )
    r = client.get("/api/factor-db/factors/JQ110:JQ110_beta/values", headers={"X-FactorDB-API-Key": "scoped-key"})
    assert r.status_code == 403
    assert "无权访问" in r.json["error"]


def test_customer_policy_can_forbid_value_export(client, monkeypatch):
    monkeypatch.setenv(
        "FACTOR_DB_CUSTOMER_POLICIES_JSON",
        json.dumps(
            [
                {
                    "customer_id": "no-export-client",
                    "name": "No Export Client",
                    "api_key": "no-export-key",
                    "allowed_sources": ["QAPI33"],
                    "allow_export_values": False,
                }
            ],
            ensure_ascii=False,
        ),
    )
    r = client.get(
        "/api/factor-db/factors/QAPI33:roe_ttm/export?scope=values&format=csv",
        headers={"X-FactorDB-API-Key": "no-export-key"},
    )
    assert r.status_code == 403
    assert "不允许导出" in r.json["error"]


def test_api_controlled_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setenv("FACTOR_DB_API_KEYS", "rate-limit-key")
    monkeypatch.setenv("FACTOR_DB_RATE_LIMIT_COUNT", "1")
    monkeypatch.setenv("FACTOR_DB_RATE_LIMIT_WINDOW_SECONDS", "3600")
    headers = {"X-FactorDB-API-Key": "rate-limit-key"}
    first = client.get("/api/factor-db/factors/JQ110:JQ110_beta/values", headers=headers)
    assert first.status_code == 425
    second = client.get("/api/factor-db/factors/JQ110:JQ110_beta/values", headers=headers)
    assert second.status_code == 429
    assert "频繁" in second.json["error"]


def test_customer_policy_uses_customer_specific_rate_limit(client, monkeypatch):
    monkeypatch.setenv(
        "FACTOR_DB_CUSTOMER_POLICIES_JSON",
        json.dumps(
            [
                {
                    "customer_id": "custom-limit-client",
                    "name": "Custom Limit Client",
                    "api_key": "custom-limit-key",
                    "allowed_sources": ["JQ110"],
                    "allow_export_values": True,
                    "rate_limit_count": 1,
                    "rate_limit_window_seconds": 3600,
                }
            ],
            ensure_ascii=False,
        ),
    )
    monkeypatch.setenv("FACTOR_DB_RATE_LIMIT_COUNT", "50")
    headers = {"X-FactorDB-API-Key": "custom-limit-key"}
    first = client.get("/api/factor-db/factors/JQ110:JQ110_beta/values", headers=headers)
    assert first.status_code == 425
    second = client.get("/api/factor-db/factors/JQ110:JQ110_beta/values", headers=headers)
    assert second.status_code == 429


def test_api_controlled_request_writes_audit_log(client, monkeypatch, tmp_path):
    audit_path = tmp_path / "factor_db_access.jsonl"
    monkeypatch.setenv(
        "FACTOR_DB_CUSTOMER_POLICIES_JSON",
        json.dumps(
            [
                {
                    "customer_id": "audit-client",
                    "name": "Audit Client",
                    "api_key": "audit-key",
                    "allowed_sources": ["JQ110"],
                    "allow_export_values": True,
                }
            ],
            ensure_ascii=False,
        ),
    )
    monkeypatch.setenv("FACTOR_DB_AUDIT_LOG_PATH", str(audit_path))
    monkeypatch.setenv("FACTOR_DB_RATE_LIMIT_COUNT", "100")
    headers = {"Authorization": "Bearer audit-key"}
    r = client.get("/api/factor-db/factors/JQ110:JQ110_beta/values", headers=headers)
    assert r.status_code == 425
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert lines
    payload = json.loads(lines[-1])
    assert payload["endpoint"] == "values"
    assert payload["factor_id"] == "JQ110:JQ110_beta"
    assert payload["client_id"] == "audit-client"
    assert payload["customer_name"] == "Audit Client"
    assert payload["auth_mode"] == "customer_policy"
    assert payload["status_code"] == 425


def test_backend_app_exposes_factor_db_api(backend_client):
    r = backend_client.get("/api/factor-db/stats")
    assert r.status_code == 200
    assert r.json["total_factors"] == sum(EXPECTED_SOURCES.values())


def test_backend_app_exposes_factor_db_frontend(backend_client):
    r = backend_client.get("/factor-db/")
    assert r.status_code == 200
    assert "text/html" in r.content_type
