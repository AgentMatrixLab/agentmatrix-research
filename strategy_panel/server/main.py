"""
QUANT DESK 后端 API — FastAPI + BigQuant 引擎

11 个端点覆盖策略总览/上传/回测/组合/交易/持仓/风险
内存/CPU 策略: SQLite WAL + Parquet 惰性读取 + 单 Worker 回测 + 结果缓存
"""
import os, sys, json, time, math, uuid, re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# 注入引擎模块路径（仅 engine_adapter 使用时才需要）
# 注意：不注入 sys.path 以免覆盖本地的 config.py
ENGINE_DIR = r"D:\bigquant\custom_engine"

from config import (
    DATA_DIR, INIT_CAPITAL,
    BENCHMARK_MAP,
)
from db import get_db, init_db, seed_data


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    seed_data()
    yield


app = FastAPI(title="QUANT DESK API", version="1.0", lifespan=lifespan)

# CORS — 放行前端开发端口
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════
# 请求/响应模型
# ══════════════════════════════════════════

class BacktestParams(BaseModel):
    file_id: Optional[str] = None
    strategy_id: Optional[str] = None
    start: str = "2020-01-01"
    end: str = "2026-07-30"
    capital: float = INIT_CAPITAL
    benchmark: str = "csi300"
    fee_rate: float = 0.00025
    slippage: float = 0.001
    symbols: list = []  # 指定股票池，空则自动选 8 只
    source_code: Optional[str] = None

class PortfolioBacktestRequest(BaseModel):
    items: list  # [{strategyId, weight}]
    rebalance: str = "monthly"
    start: str = "2020-01-01"
    end: str = "2026-07-30"


# ══════════════════════════════════════════
# 1. 策略列表
# ══════════════════════════════════════════
@app.get("/api/strategies")
def list_strategies():
    db = get_db()
    rows = db.execute("SELECT id, name, tag, status, version FROM strategies ORDER BY id").fetchall()

    # 附加上今日收益 + KPI + spark 迷你曲线 (最近 30 个净值点)
    strategies = []
    db2 = get_db()
    for r in rows:
        sid = r["id"]
        if sid == "folio":
            continue  # 动态组合策略已由 /api/overview 提供
        # 今日收益
        nav_row = db2.execute(
            "SELECT nav FROM nav_series WHERE strategy_id=? ORDER BY date DESC LIMIT 2", [sid]
        ).fetchall()
        today_ret = 0.0
        if len(nav_row) >= 2:
            today_ret = round(float(nav_row[0]["nav"]) / float(nav_row[1]["nav"]) - 1, 4)

        # KPI
        annual_ret = 0.0
        sharpe = 0.0
        kpi = db2.execute("SELECT annual_return, sharpe FROM kpis WHERE strategy_id=?", [sid]).fetchone()
        if kpi:
            annual_ret = kpi["annual_return"]
            sharpe = kpi["sharpe"]

        # spark — 最近 30 个净值点（等距采样）
        spark_navs = db2.execute(
            "SELECT nav FROM nav_series WHERE strategy_id=? ORDER BY date ASC", [sid]
        ).fetchall()
        spark = []
        if len(spark_navs) >= 2:
            step = max(1, len(spark_navs) // 30)
            spark = [float(spark_navs[i]["nav"]) for i in range(0, len(spark_navs), step)][:30]

        strategies.append({
            "id": r["id"], "name": r["name"], "tag": r["tag"],
            "status": r["status"], "version": r["version"],
            "annualReturn": annual_ret, "sharpe": sharpe, "todayReturn": today_ret,
            "spark": spark,
        })
    db2.close()
    return strategies


# ── 策略总览（组合 + 个体分离） ──
@app.get("/api/overview")
def overview():
    """
    返回分组结构:
      folio: 自动选 Top5 策略 → 逆波动率加权 → 合成组合净值
      strategies: 所有个体策略（按年化收益降序）
    """
    import numpy as np

    db = get_db()

    # ── 1. 查询所有策略 KPI ──
    rows = db.execute("""
        SELECT s.id, s.name, s.tag, s.status, s.version,
               k.total_return, k.annual_return, k.sharpe, k.max_drawdown, k.volatility
        FROM strategies s
        LEFT JOIN kpis k ON s.id = k.strategy_id
        ORDER BY k.annual_return DESC
    """).fetchall()

    # ── 2. 个体策略列表（含今日收益 + spark） ──
    strategies = []
    nav_maps = {}
    for r in rows:
        sid = r["id"]
        if sid == "folio":
            continue  # folio 本身不作为个体策略展示

        # 今日收益
        nav_row = db.execute(
            "SELECT nav FROM nav_series WHERE strategy_id=? ORDER BY date DESC LIMIT 2", [sid]
        ).fetchall()
        today_ret = 0.0
        if len(nav_row) >= 2 and nav_row[0]["nav"] > 0:
            today_ret = round(float(nav_row[0]["nav"]) / float(nav_row[1]["nav"]) - 1, 4)

        # 迷你曲线
        spark_navs = db.execute(
            "SELECT nav FROM nav_series WHERE strategy_id=? ORDER BY date ASC", [sid]
        ).fetchall()
        spark = []
        if len(spark_navs) >= 2:
            step = max(1, len(spark_navs) // 30)
            spark = [float(spark_navs[i]["nav"]) for i in range(0, len(spark_navs), step)][:30]

        # 加载完整净值用于组合计算
        nav_full = db.execute(
            "SELECT date, nav FROM nav_series WHERE strategy_id=? ORDER BY date", [sid]
        ).fetchall()
        nav_maps[sid] = {r2["date"]: r2["nav"] for r2 in nav_full}

        strategies.append({
            "id": sid, "name": r["name"], "tag": r["tag"],
            "status": r["status"], "version": r["version"],
            "annualReturn": round(r["annual_return"] or 0, 4),
            "totalReturn": round(r["total_return"] or 0, 4),
            "sharpe": round(r["sharpe"] or 0, 2),
            "maxDrawdown": round(abs(r["max_drawdown"] or 0), 4),
            "volatility": round(r["volatility"] or 0, 4),
            "todayReturn": today_ret,
            "spark": spark,
        })

    # ── 3. 自动合成组合: Top5 + 逆波动率加权 ──
    # 尝试所有可能组合，找出重叠日期 >= 20 天且策略数最多的组合
    import itertools

    top5 = strategies[:5]
    folio = None

    if len(top5) >= 2:
        best_combo = None
        best_navs = None
        best_dates = None
        best_count = 0
        best_overlap = 0

        # 从大到小尝试组合大小 (5 → 4 → 3 → 2)
        for combo_size in range(min(len(top5), 5), 1, -1):
            for combo in itertools.combinations(range(len(top5)), combo_size):
                candidates = [top5[i] for i in combo]
                cand_navs = {s["id"]: nav_maps[s["id"]] for s in candidates
                             if s["id"] in nav_maps and nav_maps[s["id"]]}
                if len(cand_navs) < 2:
                    continue

                common_dates = sorted(set.intersection(*[set(m.keys()) for m in cand_navs.values()]))
                if len(common_dates) >= 20:
                    # 优先选策略数多，同策略数时选重叠天数多（避免短历史策略）
                    if len(cand_navs) > best_count or \
                       (len(cand_navs) == best_count and len(common_dates) > best_overlap):
                        best_count = len(cand_navs)
                        best_overlap = len(common_dates)
                        best_combo = candidates
                        best_navs = cand_navs
                        best_dates = common_dates

            if best_combo is not None:
                break  # 找到最大策略数的可用组合就停

        if best_combo is not None:
            top5_navs = best_navs
            common_dates = best_dates

            # 逆波动率权重
            vols = {}
            for sid in top5_navs:
                navs = np.array([top5_navs[sid][d] for d in common_dates])
                daily_ret = navs[1:] / navs[:-1] - 1
                ann_vol = float(np.std(daily_ret, ddof=1) * np.sqrt(252))
                if ann_vol > 0:
                    vols[sid] = ann_vol

            if vols:
                inv_vols = {sid: 1.0 / v for sid, v in vols.items()}
                total_inv = sum(inv_vols.values())
                weights = {sid: round(w / total_inv, 4) for sid, w in inv_vols.items()}

                # 合成组合净值
                prev_vals = {sid: top5_navs[sid][common_dates[0]] for sid in weights}
                combined_navs = [1.0]
                combined_dates = [common_dates[0]]
                prev_combined = 1.0

                for d in common_dates[1:]:
                    daily_ret = 0.0
                    for sid in weights:
                        if d in top5_navs[sid] and prev_vals[sid] > 0:
                            ret = top5_navs[sid][d] / prev_vals[sid] - 1
                            daily_ret += weights[sid] * ret
                            prev_vals[sid] = top5_navs[sid][d]
                    prev_combined *= (1 + daily_ret)
                    combined_navs.append(round(prev_combined, 6))
                    combined_dates.append(d)

                # 组合 KPI
                navs = np.array(combined_navs)
                daily_rets = navs[1:] / navs[:-1] - 1
                n_days = len(daily_rets)
                ann_vol_f = float(np.std(daily_rets, ddof=1) * np.sqrt(252))
                sharpe_f = float(np.mean(daily_rets) / np.std(daily_rets, ddof=1) * np.sqrt(252)) if ann_vol_f > 0 else 0
                peak_f = np.maximum.accumulate(navs)
                dd_f = (navs - peak_f) / peak_f * 100
                mdd_f = float(np.min(dd_f))
                years_f = n_days / 252
                ann_ret_f = float(navs[-1] ** (1 / years_f) - 1) * 100 if years_f > 0 else 0
                tot_ret_f = float((navs[-1] - 1) * 100)

                # 迷你曲线
                spark_step = max(1, len(combined_navs) // 30)
                folio_spark = [combined_navs[i] for i in range(0, len(combined_navs), spark_step)][:30]

                # 今日收益
                folio_today = 0.0
                if len(combined_navs) >= 2:
                    folio_today = round(combined_navs[-1] / combined_navs[-2] - 1, 4)

                folio = {
                    "id": "folio",
                    "name": "综合组合(Top5逆波动率)",
                    "tag": "组合",
                    "status": "running",
                    "version": "auto",
                    "annualReturn": round(ann_ret_f / 100, 4),
                    "totalReturn": round(tot_ret_f / 100, 4),
                    "sharpe": round(sharpe_f, 2),
                    "maxDrawdown": round(abs(mdd_f) / 100, 4),
                    "volatility": round(ann_vol_f, 4),
                    "todayReturn": folio_today,
                    "spark": folio_spark,
                    "weights": weights,
                    "navDates": combined_dates,
                    "navValues": combined_navs,
                }

    db.close()
    return {"folio": folio, "strategies": strategies}


# ── 策略源码 ──
@app.get("/api/strategies/{strategy_id}/source")
def get_strategy_source(strategy_id: str):
    db = get_db()
    row = db.execute("SELECT source_code FROM strategies WHERE id=?", [strategy_id]).fetchone()
    if not row or not row["source_code"]:
        raise HTTPException(404, "该策略无源码")
    return {"id": strategy_id, "sourceCode": row["source_code"]}


# ══════════════════════════════════════════
# 2. 策略详情（总览页全量数据）
# ══════════════════════════════════════════
@app.get("/api/strategies/{strategy_id}")
def get_strategy(strategy_id: str, period: str = "all", benchmark: str = "csi300"):
    db = get_db()

    # 策略元数据
    s = db.execute("SELECT * FROM strategies WHERE id=?", [strategy_id]).fetchone()
    if not s:
        db.close()
        raise HTTPException(404, "策略不存在")

    # KPI
    kpi = db.execute("SELECT * FROM kpis WHERE strategy_id=?", [strategy_id]).fetchone()
    kpis = dict(kpi) if kpi else {}

    # 净值序列 — 按周期过滤
    nav_rows = db.execute(
        "SELECT date, nav, benchmark_nav, drawdown FROM nav_series WHERE strategy_id=? ORDER BY date",
        [strategy_id]
    ).fetchall()

    nav_data = [{"date": r["date"], "nav": r["nav"], "benchmark": r["benchmark_nav"], "drawdown": r["drawdown"]}
                for r in nav_rows]
    nav_data = _filter_by_period(nav_data, period)

    # 持仓
    hold_rows = db.execute(
        "SELECT * FROM holdings WHERE strategy_id=? ORDER BY value DESC", [strategy_id]
    ).fetchall()
    holdings = [dict(r) for r in hold_rows]
    # 兼容前端 camelCase
    for h in holdings:
        if "pnl_pct" in h:
            h["pnlPct"] = h.pop("pnl_pct")

    # 成交
    trade_rows = db.execute(
        "SELECT * FROM trades WHERE strategy_id=? ORDER BY time DESC LIMIT 50", [strategy_id]
    ).fetchall()
    trades = [dict(r) for r in trade_rows]

    # 子策略（仅红利策略有）
    sub_strategies = _get_sub_strategies(strategy_id)

    db.close()

    return {
        "id": strategy_id,
        "name": s["name"],
        "tag": _col(s, "tag", ""),
        "status": _col(s, "status", "running"),
        "version": _col(s, "version", ""),
        "nav": nav_data,
        "kpis": {
            "totalReturn": kpis.get("total_return", 0),
            "annualReturn": kpis.get("annual_return", 0),
            "sharpe": kpis.get("sharpe", 0),
            "maxDrawdown": kpis.get("max_drawdown", 0),
            "winRate": kpis.get("win_rate", 0),
            "volatility": kpis.get("volatility", 0),
            "alpha": kpis.get("alpha", 0),
            "beta": kpis.get("beta", 0),
            "sortino": kpis.get("sortino", 0),
            "calmar": kpis.get("calmar", 0),
        },
        "holdings": holdings,
        "trades": trades,
        "subStrategies": sub_strategies,
    }


def _col(row, col, default=None):
    """sqlite3.Row 安全取值"""
    try:
        return row[col]
    except (KeyError, IndexError):
        return default


def _filter_by_period(nav_data: list, period: str) -> list:
    if not nav_data:
        return nav_data
    if period == "all":
        return nav_data
    today = datetime.now().date()
    deltas = {"1M": 30, "3M": 90, "6M": 180, "YTD": 365, "1Y": 365}
    days = deltas.get(period, 0)
    if days == 0:
        return nav_data
    cutoff = (today - timedelta(days=days)).isoformat()
    return [n for n in nav_data if n["date"] >= cutoff] or nav_data[-20:]


def _get_sub_strategies(strategy_id: str) -> list:
    """子策略（暂固定，后续可从 DB 读）"""
    if strategy_id == "div_v6":
        return [
            {"id": "dividend", "name": "高股息龙头", "weight": 0.28, "contribution": 0.12},
            {"id": "lowvol", "name": "红利低波", "weight": 0.22, "contribution": 0.08},
            {"id": "quality", "name": "红利质量", "weight": 0.20, "contribution": 0.06},
            {"id": "growth", "name": "红利成长", "weight": 0.18, "contribution": 0.04},
            {"id": "momentum", "name": "红利动量", "weight": 0.12, "contribution": 0.02},
        ]
    if strategy_id == "micro_cap":
        return [
            {"id": "micro_value", "name": "小市值价值", "weight": 0.35, "contribution": 0.05},
            {"id": "micro_reversal", "name": "小市值反转", "weight": 0.35, "contribution": 0.03},
            {"id": "micro_quality", "name": "小市值质量", "weight": 0.30, "contribution": 0.01},
        ]
    return []


# ══════════════════════════════════════════
# 3. 上传策略
# ══════════════════════════════════════════
@app.post("/api/strategies/upload")
async def upload_strategy(file: UploadFile = File(...)):
    """上传回测策略。格式: bt.Strategy 子类，含 def next(self)"""
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(400, "只接受 .py 文件")

    content = await file.read()
    try:
        source = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "文件编码必须是 UTF-8")

    from engine_adapter import validate
    parsed_ok, message = validate(source)

    return {
        "fileId": f"file_{uuid.uuid4().hex[:7]}",
        "name": file.filename,
        "size": len(content),
        "parsedOk": parsed_ok,
        "message": message,
    }


# ══════════════════════════════════════════
# 4-6. 回测任务（提交 / 列表 / 状态 / 结果）
# ══════════════════════════════════════════
@app.post("/api/backtests")
def submit_backtest(params: BacktestParams):
    source_code = params.source_code or ""
    strategy_name = params.file_id or params.strategy_id or "unnamed"
    file_name = params.file_id or ""

    from job_queue import submit_job
    symbols_list = list(params.symbols) if params.symbols else []
    job_id = submit_job(
        get_db, source_code, strategy_name, file_name,
        {"start": params.start, "end": params.end, "capital": params.capital,
         "benchmark": params.benchmark, "fee_rate": params.fee_rate, "slippage": params.slippage,
         "symbols": symbols_list}
    )
    return {"jobId": job_id}


@app.get("/api/backtests")
def list_backtest_jobs(page: int = 1, page_size: int = 20):
    db = get_db()
    offset = (page - 1) * page_size
    rows = db.execute(
        "SELECT * FROM backtest_jobs ORDER BY submitted_at DESC LIMIT ? OFFSET ?",
        [page_size, offset]
    ).fetchall()
    total = db.execute("SELECT COUNT(*) FROM backtest_jobs").fetchone()[0]
    db.close()
    return {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "rows": [_format_job(r) for r in rows],
    }


@app.get("/api/backtests/{job_id}")
def get_backtest_status(job_id: str):
    db = get_db()
    r = db.execute("SELECT * FROM backtest_jobs WHERE id=?", [job_id]).fetchone()
    db.close()
    if not r:
        raise HTTPException(404, "任务不存在")
    return _format_job(r)


@app.get("/api/backtests/{job_id}/result")
def get_backtest_result(job_id: str):
    db = get_db()
    r = db.execute("SELECT * FROM backtest_jobs WHERE id=?", [job_id]).fetchone()
    db.close()
    if not r:
        raise HTTPException(404, "任务不存在")
    if r["status"] != "done":
        raise HTTPException(400, f"任务未完成 (当前状态: {r['status']})")

    params = json.loads(r["params"])
    result = params.get("result", {})
    return {
        "id": r["id"],
        "strategyName": r["strategy_name"],
        "nav": result.get("nav", []),
        "kpis": result.get("kpis", {}),
        "holdings": result.get("holdings", []),
        "trades": result.get("trades", []),
    }


def _format_job(r) -> dict:
    return {
        "id": r["id"],
        "strategyName": r["strategy_name"],
        "status": r["status"],
        "progress": r["progress"],
        "submittedAt": r["submitted_at"],
        "durationMs": r["duration_ms"],
        "resultId": r["result_id"],
        "error": r["error"] or "",
    }


# ══════════════════════════════════════════
# 7. 组合回测
# ══════════════════════════════════════════
@app.post("/api/portfolio/backtest")
def portfolio_backtest(req: PortfolioBacktestRequest):
    """
    加权组合回测：按日频将各策略日收益加权合成
    """
    if not req.items:
        raise HTTPException(400, "至少选择一个策略")

    # 校验权重
    total_w = sum(it.get("weight", 0) for it in req.items)
    if abs(total_w - 1.0) > 0.001:
        raise HTTPException(400, f"权重之和必须为 1 (当前: {total_w})")

    db = get_db()

    # 加载各策略净值
    all_dates = set()
    strategy_navs = {}
    for it in req.items:
        sid = it.get("strategyId", "")
        rows = db.execute(
            "SELECT date, nav FROM nav_series WHERE strategy_id=? ORDER BY date", [sid]
        ).fetchall()
        if not rows:
            db.close()
            raise HTTPException(404, f"策略 {sid} 无数据")

        nav_map = {}
        for r in rows:
            d = r["date"]
            nav_map[d] = r["nav"]
            all_dates.add(d)
        strategy_navs[sid] = (it["weight"], nav_map)

    dates = sorted(all_dates)
    # 日期过滤
    if req.start:
        dates = [d for d in dates if d >= req.start]
    if req.end:
        dates = [d for d in dates if d <= req.end]

    # 合成组合净值
    combined_nav = []
    bench_nav = []
    first_nav = None
    peak = 0
    for d in dates:
        nav_sum = 0
        bench_sum = 0
        valid = False
        for sid, (weight, nav_map) in strategy_navs.items():
            if d in nav_map:
                nav_sum += weight * nav_map[d]
                bench_sum += weight * nav_map[d]  # 近似
                valid = True
        if not valid:
            continue

        if first_nav is None:
            first_nav = nav_sum
        norm = nav_sum / first_nav if first_nav > 0 else 1.0
        bench_norm = bench_sum / first_nav if first_nav > 0 else 1.0
        peak = max(peak, norm)
        dd = norm / peak - 1 if peak > 0 else 0
        combined_nav.append({
            "date": d, "nav": round(norm, 4),
            "benchmark": round(bench_norm, 4),
            "drawdown": round(dd, 4),
        })

    db.close()

    # KPI
    import numpy as np
    from engine_adapter import _compute_kpis
    kpis = _compute_kpis(np, combined_nav)

    return {
        "kpis": {k: (round(float(v), 4) if isinstance(v, (int, float)) else v)
                 for k, v in kpis.items()},
        "nav": combined_nav,
        "weights": req.items,
    }


# ══════════════════════════════════════════
# 8. 交易记录
# ══════════════════════════════════════════
@app.get("/api/trades")
def list_trades(
    strategy_id: str = Query("alpha", alias="strategyId"),
    side: str = Query(""),
    q: str = Query(""),
    page: int = Query(1),
    page_size: int = Query(20, alias="pageSize"),
):
    db = get_db()
    conditions = ["strategy_id = ?"]
    params = [strategy_id]

    if side:
        conditions.append("side = ?")
        params.append(side)
    if q:
        conditions.append("(code LIKE ? OR name LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])

    where = " AND ".join(conditions)
    total = db.execute(f"SELECT COUNT(*) FROM trades WHERE {where}", params).fetchone()[0]

    offset = (page - 1) * page_size
    rows = db.execute(
        f"SELECT * FROM trades WHERE {where} ORDER BY time DESC LIMIT ? OFFSET ?",
        params + [page_size, offset]
    ).fetchall()
    db.close()

    return {
        "total": total, "page": page, "pageSize": page_size,
        "rows": [dict(r) for r in rows],
    }


# ══════════════════════════════════════════
# 9. 持仓分析
# ══════════════════════════════════════════
@app.get("/api/positions")
def get_positions(strategy_id: str = Query("alpha", alias="strategyId")):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM holdings WHERE strategy_id=? ORDER BY value DESC", [strategy_id]
    ).fetchall()

    holdings = [dict(r) for r in rows]
    # 兼容前端 camelCase: pnl_pct → pnlPct
    for h in holdings:
        if "pnl_pct" in h:
            h["pnlPct"] = h.pop("pnl_pct")
    n = len(holdings)
    total_w = sum(h["weight"] for h in holdings)
    top5 = sorted(holdings, key=lambda x: x["weight"], reverse=True)[:5]
    top5_w = sum(h["weight"] for h in top5)
    hhi = sum((h["weight"] / total_w) ** 2 for h in holdings) if total_w > 0 else 0

    # 行业分布（简单统计）
    industries = {}
    for h in holdings:
        ind = h.get("industry", "综合")
        industries[ind] = industries.get(ind, 0) + h.get("weight", 0)
    industry_list = sorted(
        [{"name": k, "weight": round(v, 4)} for k, v in industries.items()],
        key=lambda x: x["weight"], reverse=True
    )

    # 市值风格（Mock: 按权重近似）
    market_cap = [
        {"label": "大盘", "weight": round(top5_w, 4)},
        {"label": "中盘", "weight": round((total_w - top5_w) * 0.6, 4)},
        {"label": "小盘", "weight": round((total_w - top5_w) * 0.4, 4)},
    ]

    db.close()
    return {
        "count": n,
        "totalWeight": round(total_w, 4),
        "top5Weight": round(top5_w, 4),
        "hhi": round(hhi, 4),
        "industries": industry_list or [{"name": "综合", "weight": total_w}],
        "marketCap": market_cap,
        "rows": holdings,
    }


# ══════════════════════════════════════════
# 10. 风险监控
# ══════════════════════════════════════════
@app.get("/api/risk/overview")
def risk_overview(strategy_id: str = Query("alpha")):
    db = get_db()

    # 当前回撤
    nav_row = db.execute(
        "SELECT nav, drawdown FROM nav_series WHERE strategy_id=? ORDER BY date DESC LIMIT 1",
        [strategy_id]
    ).fetchone()
    current_dd = nav_row["drawdown"] if nav_row else 0

    # KPI
    kpi_raw = db.execute("SELECT * FROM kpis WHERE strategy_id=?", [strategy_id]).fetchone()
    kpi = dict(kpi_raw) if kpi_raw else {}

    # 预警
    alerts = db.execute(
        "SELECT * FROM alerts WHERE strategy_id=? OR strategy_id='alpha'",
        [strategy_id]
    ).fetchall()
    alert_list = [dict(a) for a in alerts]

    # 回撤事件（从净值序列识别）
    nav_rows_raw = db.execute(
        "SELECT date, nav, drawdown FROM nav_series WHERE strategy_id=? ORDER BY date",
        [strategy_id]
    ).fetchall()
    nav_rows = [dict(r) for r in nav_rows_raw]
    drawdown_events = _identify_drawdown_events(nav_rows)

    # 月度收益
    monthly = _calc_monthly_returns(nav_rows)

    db.close()

    return {
        "currentDrawdown": round(float(current_dd), 4),
        "var95": round(float(kpi["volatility"]) * 1.645 if kpi else 0.02, 4),
        "volatility": float(kpi["volatility"]) if kpi else 0.15,
        "beta": float(kpi.get("beta", 0.7)),
        "leverage": 1.0,
        "alerts": alert_list,
        "drawdownEvents": drawdown_events,
        "monthlyReturns": monthly,
    }


def _identify_drawdown_events(nav_rows: list) -> list:
    events = []
    in_dd = False
    start_date = ""
    peak = 0
    trough_date = ""
    trough_depth = 0.0
    for r in nav_rows:
        nav = r["nav"]
        if nav > peak:
            if in_dd and trough_depth < -0.02:
                events.append({
                    "start": start_date,
                    "trough": trough_date,
                    "recovered": r["date"],
                    "depth": round(trough_depth, 4),
                    "durationDays": (datetime.strptime(r["date"], "%Y-%m-%d") -
                                     datetime.strptime(start_date, "%Y-%m-%d")).days,
                })
            peak = nav
            in_dd = False
            trough_depth = 0.0
        else:
            dd = nav / peak - 1 if peak > 0 else 0
            if dd < -0.02:
                if not in_dd:
                    in_dd = True
                    start_date = r["date"]
                if dd < trough_depth:
                    trough_depth = dd
                    trough_date = r["date"]
    return events[-5:]


def _calc_monthly_returns(nav_rows: list) -> list:
    if not nav_rows:
        return []
    monthly = {}
    for r in nav_rows:
        m = r["date"][:7]
        monthly[m] = r["nav"]
    sorted_months = sorted(monthly.keys())
    rets = []
    for i in range(1, len(sorted_months)):
        prev_m, cur_m = sorted_months[i-1], sorted_months[i]
        ret = monthly[cur_m] / monthly[prev_m] - 1
        rets.append({"month": cur_m, "ret": round(ret, 4)})
    return rets[-12:]


# ══════════════════════════════════════════
# 11. 组合保存 (optional)
# ══════════════════════════════════════════
@app.get("/api/portfolios")
def list_portfolios():
    db = get_db()
    rows = db.execute("SELECT * FROM portfolios ORDER BY created_at DESC").fetchall()
    db.close()
    return [{"id": r["id"], "name": r["name"], "items": json.loads(r["items"]),
             "createdAt": r["created_at"]} for r in rows]


@app.post("/api/portfolios")
def save_portfolio(data: dict):
    db = get_db()
    db.execute(
        "INSERT INTO portfolios (name, items) VALUES (?,?)",
        [data.get("name", "未命名"), json.dumps(data.get("items", []))]
    )
    db.commit()
    db.close()
    return {"ok": True}


# ══════════════════════════════════════════
# 健康检查
# ══════════════════════════════════════════
@app.get("/api/health")
def health():
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]
    db.close()
    return {
        "status": "ok",
        "strategies": count,
        "engine": "Backtrader (via engine_adapter)",
        "data_dir": DATA_DIR,
    }


# ── 前端静态文件 + SPA 回退 ──
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

@app.middleware("http")
async def spa_middleware(request, call_next):
    """SPA 回退：非 API / 非静态资源 → index.html"""
    response = await call_next(request)
    if response.status_code == 404 and not request.url.path.startswith("/api"):
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
    return response

if os.path.isdir(STATIC_DIR) and os.path.isfile(os.path.join(STATIC_DIR, "index.html")):
    # html=True: 为目录请求自动返回 index.html
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


# ── 入口 ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100, log_level="info")
