"""factor_db 元数据与 API 回归测试。

覆盖：目录统计（含 qlib-factor-zoo 来源）、检索、详情、字典、
Flask 端点（含 zoo 因子值未就绪时的 425 语义）。
"""

from __future__ import annotations

import pytest

flask = pytest.importorskip("flask")

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


@pytest.fixture(scope="module")
def client():
    app = create_app()
    return app.test_client()


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


def test_api_zoo_factor_values_not_ready(client):
    """zoo 来源因子值未生成时返回 425（早期数据不可用语义）。"""
    r = client.get("/api/factor-db/factors/JQ110:JQ110_beta/values")
    assert r.status_code == 425
    assert "qlib" in r.json["error"]


def test_api_distribution_demo(client):
    r = client.get("/api/factor-db/factors/GTJA191:GTJA001/distribution?demo=1")
    assert r.status_code == 200
    assert r.json["demo"] is True


def test_api_dictionary(client):
    r = client.get("/api/factor-db/dictionary")
    assert r.status_code == 200
    assert r.json["count"] == sum(EXPECTED_SOURCES.values())
