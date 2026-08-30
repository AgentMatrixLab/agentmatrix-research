"""Factor DB 数据服务层。

因子值查询经 Quant API v2（read-only client）代理，token 由后端环境变量注入，
前端与导出文件中不出现任何凭证。分布统计在本地对最新月频截面计算。
"""

from __future__ import annotations

import math
from typing import Any

from research_core.data_loader.quant_api_client import QuantApiClient, QuantApiError
from research_core.factor_db.metadata import get_factor


class FactorDataError(RuntimeError):
    """因子数据查询失败（token 缺失、远端不可达、因子无数据等）。"""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def _quant_name(factor_id: str) -> str:
    """把产品 factor_id 转为 Quant API factor_monthly 的因子名。"""
    row = get_factor(factor_id)
    if row is None:
        raise FactorDataError(f"未知因子: {factor_id}", status_code=404)
    if not row["factor_id"].startswith("QAPI33:"):
        raise FactorDataError(
            f"因子 {factor_id} 的因子值数据尚未就绪"
            "（Alpha101 需经 RQData 拉取任务生成；"
            "GTJA191/TDXGS/JQ110/Alpha158/Alpha360（qlib-factor-zoo 来源）需 Qlib 数据环境经 qlib_lab 计算生成）",
            status_code=425,
        )
    return row["factor_id"].split(":", 1)[1]


def _client() -> QuantApiClient:
    client = QuantApiClient()
    if not client.config.token_configured:
        raise FactorDataError(
            "Quant API token 未配置（请设置环境变量 FACTOR_LAB_QUANT_API_TOKEN 或 QUANT_API_TOKEN）",
            status_code=401,
        )
    return client


def factor_values(
    factor_id: str,
    *,
    symbol: str | None = None,
    date: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """查询因子值时序/截面（真实数据，经 Quant API v2 factor_monthly）。"""
    name = _quant_name(factor_id)
    client = _client()
    params: dict[str, Any] = {"factor": name}
    if symbol:
        params["symbol"] = symbol
    if date:
        params["date"] = date
    if limit:
        params["limit"] = limit
    try:
        payload = client.factor_monthly(params)
    except QuantApiError as exc:
        raise FactorDataError(str(exc), status_code=exc.status_code or 502) from exc
    rows = payload.get("data") or []
    return {
        "factor_id": factor_id,
        "factor_name": name,
        "symbol": symbol,
        "date": date,
        "count": len(rows),
        "data": rows,
    }


def factor_distribution(factor_id: str, *, demo: bool = False, bins: int = 30) -> dict[str, Any]:
    """因子最新截面的分布统计：描述统计 + 直方图分箱。

    demo=True 时基于正态代理样本生成演示分布（明确标注，不冒充真实数据），
    便于无 token 环境演示产品形态。
    """
    row = get_factor(factor_id)
    if row is None:
        raise FactorDataError(f"未知因子: {factor_id}", status_code=404)

    values: list[float]
    trade_date: str
    is_demo = False

    if demo:
        import random

        rng = random.Random(hash(factor_id) & 0xFFFFFFFF)
        values = [rng.gauss(0.0, 1.0) for _ in range(4000)]
        trade_date = "demo"
        is_demo = True
    else:
        name = _quant_name(factor_id)
        client = _client()
        try:
            dates_payload = client.factor_monthly_dates()
            dates = dates_payload.get("dates") or dates_payload.get("data") or []
            if not dates:
                raise FactorDataError("Quant API 未返回任何月频日期", status_code=502)
            trade_date = str(dates[0]) if not isinstance(dates[0], dict) else str(dates[0].get("date") or dates[0])
            payload = client.factor_monthly({"factor": name, "date": trade_date})
        except QuantApiError as exc:
            raise FactorDataError(str(exc), status_code=exc.status_code or 502) from exc
        rows = payload.get("data") or []
        values = [
            float(item.get(name))
            for item in rows
            if item.get(name) is not None and not (isinstance(item.get(name), float) and math.isnan(item.get(name)))
        ]
        if not values:
            raise FactorDataError(f"因子 {factor_id} 在 {trade_date} 截面无有效数据", status_code=404)

    stats = _describe(values)
    histogram = _histogram(values, bins=bins)
    return {
        "factor_id": factor_id,
        "name_cn": row["name_cn"],
        "trade_date": trade_date,
        "sample_count": len(values),
        "demo": is_demo,
        "note": "演示数据（正态代理样本），非真实因子值" if is_demo else "真实数据（Quant API v2 factor_monthly 最新截面）",
        "stats": stats,
        "histogram": histogram,
    }


def _describe(values: list[float]) -> dict[str, Any]:
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / max(n - 1, 1)
    std = variance**0.5
    sorted_vals = sorted(values)
    p1 = _percentile(sorted_vals, 1)
    p5 = _percentile(sorted_vals, 5)
    p25 = _percentile(sorted_vals, 25)
    p50 = _percentile(sorted_vals, 50)
    p75 = _percentile(sorted_vals, 75)
    p95 = _percentile(sorted_vals, 95)
    p99 = _percentile(sorted_vals, 99)
    skew = (sum((v - mean) ** 3 for v in values) / n) / std**3 if std > 0 else 0.0
    kurtosis = (sum((v - mean) ** 4 for v in values) / n) / std**4 - 3.0 if std > 0 else 0.0
    iqr = p75 - p25
    return {
        "count": n,
        "mean": round(mean, 6),
        "std": round(std, 6),
        "min": round(sorted_vals[0], 6),
        "max": round(sorted_vals[-1], 6),
        "p1": round(p1, 6),
        "p5": round(p5, 6),
        "p25": round(p25, 6),
        "p50": round(p50, 6),
        "p75": round(p75, 6),
        "p95": round(p95, 6),
        "p99": round(p99, 6),
        "skewness": round(skew, 4),
        "kurtosis": round(kurtosis, 4),
        "iqr": round(iqr, 6),
        "outlier_ratio_p1_p99": round(
            sum(1 for v in values if v < p1 or v > p99) / n, 6
        ),
    }


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = (len(sorted_vals) - 1) * q / 100.0
    low = int(math.floor(idx))
    high = int(math.ceil(idx))
    if low == high:
        return sorted_vals[low]
    weight = idx - low
    return sorted_vals[low] * (1 - weight) + sorted_vals[high] * weight


def _histogram(values: list[float], *, bins: int) -> list[dict[str, Any]]:
    lo, hi = min(values), max(values)
    if lo == hi:
        return [{"bin_left": lo, "bin_right": hi, "count": len(values)}]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - lo) / width), bins - 1)
        counts[idx] += 1
    return [
        {
            "bin_left": round(lo + i * width, 6),
            "bin_right": round(lo + (i + 1) * width, 6),
            "count": counts[i],
        }
        for i in range(bins)
    ]


def export_factor_data(
    factor_id: str,
    *,
    fmt: str = "csv",
    scope: str = "values",
    symbol: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """导出因子数据（CSV/Excel）。

    scope=values 导出因子值时序/截面（真实数据）；scope=meta 导出因子元数据。
    返回 {"filename", "content(bytes)", "mime", "error(可选)"}。
    """
    fmt = fmt.lower()
    if fmt not in ("csv", "xlsx", "excel"):
        raise FactorDataError(f"不支持的导出格式: {fmt}（可选 csv / xlsx）", status_code=400)

    if scope == "meta":
        return _export_rows([get_factor(factor_id) or {}], f"{factor_id.replace(':', '_')}_meta", fmt)
    if scope != "values":
        raise FactorDataError(f"不支持的导出范围: {scope}（可选 values / meta）", status_code=400)

    payload = factor_values(factor_id, symbol=symbol, date=date)
    rows = payload["data"]
    if not rows:
        raise FactorDataError("没有可导出的数据行", status_code=404)
    return _export_rows(rows, f"{factor_id.replace(':', '_')}_values", fmt)


def export_dictionary(fmt: str = "csv") -> dict[str, Any]:
    """导出全部因子的数据字典。"""
    from research_core.factor_db.metadata import dictionary_rows

    fmt = fmt.lower()
    if fmt not in ("csv", "xlsx", "excel"):
        raise FactorDataError(f"不支持的导出格式: {fmt}", status_code=400)
    return _export_rows(dictionary_rows(), "factor_db_dictionary", fmt)


def _export_rows(rows: list[dict[str, Any]], stem: str, fmt: str) -> dict[str, Any]:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover
        raise FactorDataError("pandas 未安装，无法导出", status_code=500) from exc

    df = pd.DataFrame(rows)
    if fmt == "csv":
        content = df.to_csv(index=False).encode("utf-8-sig")  # BOM 便于 Excel 直接打开中文
        return {"filename": f"{stem}.csv", "content": content, "mime": "text/csv; charset=utf-8"}

    try:
        import io as _io

        buffer = _io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="data")
        return {
            "filename": f"{stem}.xlsx",
            "content": buffer.getvalue(),
            "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
    except ImportError as exc:
        raise FactorDataError(
            "Excel 导出需要 openpyxl（pip install openpyxl），或改用 format=csv",
            status_code=500,
        ) from exc


def quant_api_status(check_remote: bool = False) -> dict[str, Any]:
    client = QuantApiClient()
    payload: dict[str, Any] = {
        "base_url": client.config.base_url,
        "token_configured": client.config.token_configured,
    }
    if check_remote:
        try:
            payload["remote_health"] = client.request_json("/health", require_token=False)
        except QuantApiError as exc:
            payload["remote_health"] = {"error": str(exc)}
    return payload
