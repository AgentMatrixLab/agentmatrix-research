"""Agent Gateway — 外部智能体统一接入因子挖掘的同步 HTTP 服务.

定位
----
让 openclaw / hermes / codex / cloudecode / Trae / WorkBuddy 等任何能发 HTTP
请求的外部 agent 以统一协议接入本仓库的挖掘闭环:

    生成表达式 → POST /mine/evaluate → 拿到 IC/ICIR/去重反馈 → 改进 → 再提交

设计原则 (遵循 AGENTS.md):
- 只做薄封装, 全部评估逻辑复用 research_core.factor_lab.auto_mining, 不重复实现
- 无 token / 无数据时自动降级合成面板并在响应里明确标注, 避免外部 agent 误信结果
- 同步短请求: evaluate 上限 64 候选, 防 agent 一次提交压垮面板计算

启动
----
    PYTHONPATH=. uvicorn research_core.factor_lab.agent_gateway:app --port 8710

端点
----
    GET  /health              存活检查 + 当前面板元信息
    GET  /mine/panel          面板元信息 (来源/日期范围/标的数/字段)
    POST /mine/evaluate       同步评估候选表达式 (核心端点)
    POST /mine/loop           完整挖掘闭环 (LLM/GP/builtin + 反馈循环)
    POST /mine/feedback        生成结构化反馈文本 (给外部 agent 的下一轮提示词)

evaluate 请求示例::

    POST /mine/evaluate
    {
      "expressions": [
        {"name": "mom_20", "expression": "Ref($close, 20) / $close - 1"},
        {"name": "bad",   "expression": "NoSuchOp($close, 5)"}
      ],
      "horizon": 5
    }

响应::

    {
      "panel_source": "synthetic",
      "synthetic_warning": "面板为合成数据, IC 数字不可用于研究结论",
      "results": [
        {"name": "mom_20", "status": "PASS", "mean_rank_ic": 0.05, ...},
        {"name": "bad",   "status": "NC",  "compile_error": "..."}
      ]
    }
"""

from __future__ import annotations

import threading
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from research_core.factor_lab.auto_mining import (
    CandidateResult,
    build_feedback,
    evaluate_candidates,
    load_panel,
    run_mining_loop,
    save_results,
)

MAX_CANDIDATES = 64

app = FastAPI(title="AgentMatrix Factor Lab — Agent Gateway", version="1.0")

# 面板加载开销大 (API 拉数/缓存读取), 进程内单例 + 懒加载 + 锁保护
_panel_lock = threading.Lock()
_panel_state: dict[str, Any] = {"panel": None, "source": None}


def _get_panel(refresh: bool = False):
    with _panel_lock:
        if _panel_state["panel"] is None or refresh:
            panel, source = load_panel(source="auto", refresh_cache=refresh)
            _panel_state["panel"] = panel
            _panel_state["source"] = source
        return _panel_state["panel"], _panel_state["source"]


# ── 请求/响应模型 ────────────────────────────────────────────────────────


class ExpressionCandidate(BaseModel):
    name: str = ""
    expression: str


class EvaluateRequest(BaseModel):
    expressions: list[ExpressionCandidate] = Field(min_length=1, max_length=MAX_CANDIDATES)
    horizon: int = 5
    ic_threshold: float = 0.02
    icir_threshold: float = 0.3
    dedup_threshold: float = 0.7


class LoopRequest(BaseModel):
    theme: str = "量价因子"
    rounds: int = 2
    count_per_round: int = 8
    mode: str = "auto"          # "auto" | "llm" | "builtin"
    horizon: int = 5
    refresh_panel: bool = False


class FeedbackRequest(BaseModel):
    expressions: list[ExpressionCandidate] = Field(min_length=1, max_length=MAX_CANDIDATES)
    horizon: int = 5


# ── 工具函数 ─────────────────────────────────────────────────────────────


def _result_dict(r: CandidateResult) -> dict[str, Any]:
    d = {
        "name": r.name,
        "expression": r.expression,
        "gtja_expression": r.gtja_expression,
        "status": r.status,        # PASS / WARN / FAIL / DUP / NC
        "mean_rank_ic": r.mean_rank_ic,
        "rank_icir": r.rank_icir,
        "ic_positive_ratio": r.ic_positive_ratio,
        "coverage": r.coverage,
        "n_dates": r.n_dates,
        "duplicate_of": r.duplicate_of,
        "duplicate_corr": r.duplicate_corr,
        "compile_error": r.compile_error or None,
    }
    if r.mean_turnover is not None:
        d["mean_turnover"] = r.mean_turnover
    if r.report is not None and r.report.warnings:
        d["warnings"] = list(r.report.warnings)
    return d


def _panel_meta(panel, source: str) -> dict[str, Any]:
    return {
        "panel_source": source,             # cache / api / parquet / synthetic
        "synthetic": source == "synthetic",
        "n_dates": int(panel["date"].nunique()),
        "n_codes": int(panel["code"].nunique()),
        "date_min": str(panel["date"].min()),
        "date_max": str(panel["date"].max()),
        "columns": list(panel.columns),
    }


def _synthetic_notice(source: str) -> str | None:
    if source == "synthetic":
        return ("当前面板为合成数据(无 API token 且无缓存), IC 数字仅用于管线自检, "
                "不可作为研究结论。配置 FACTOR_LAB_QUANT_API_TOKEN 后重启 gateway。")
    return None


# ── 端点 ─────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "agent_gateway", "max_candidates": MAX_CANDIDATES}


@app.get("/mine/panel")
def panel_info(refresh: bool = False) -> dict[str, Any]:
    panel, source = _get_panel(refresh=refresh)
    meta = _panel_meta(panel, source)
    meta["synthetic_warning"] = _synthetic_notice(source)
    return meta


@app.post("/mine/evaluate")
def evaluate(req: EvaluateRequest) -> dict[str, Any]:
    """同步评估候选表达式: 编译 → 真实 IC → 去重 → 状态判定, 一次调用返回全部反馈。"""
    panel, source = _get_panel()
    candidates = [{"name": c.name or f"factor_{i}", "expression": c.expression}
                  for i, c in enumerate(req.expressions)]
    results = evaluate_candidates(
        panel, candidates,
        horizon=req.horizon,
        ic_threshold=req.ic_threshold,
        icir_threshold=req.icir_threshold,
        dedup_threshold=req.dedup_threshold,
    )
    return {
        "panel_source": source,
        "synthetic_warning": _synthetic_notice(source),
        "thresholds": {
            "ic": req.ic_threshold, "icir": req.icir_threshold, "dedup": req.dedup_threshold,
        },
        "results": [_result_dict(r) for r in results],
    }


@app.post("/mine/feedback")
def feedback(req: FeedbackRequest) -> dict[str, Any]:
    """把评估结果转成结构化反馈文本 — 外部 agent 可直接拼进下一轮提示词。"""
    panel, source = _get_panel()
    candidates = [{"name": c.name or f"factor_{i}", "expression": c.expression}
                  for i, c in enumerate(req.expressions)]
    results = evaluate_candidates(panel, candidates, horizon=req.horizon)
    return {
        "panel_source": source,
        "feedback": build_feedback(results),
        "results": [_result_dict(r) for r in results],
    }


@app.post("/mine/loop")
def loop(req: LoopRequest) -> dict[str, Any]:
    """完整挖掘闭环 (内置/LLM 候选生成 + 反馈迭代), 并落盘 runtime/mining_runs/。"""
    panel, source = _get_panel(refresh=req.refresh_panel)
    out = run_mining_loop(
        panel,
        theme=req.theme,
        rounds=req.rounds,
        count_per_round=req.count_per_round,
        mode=req.mode,
        horizon=req.horizon,
    )
    csv_path = save_results(out, panel_source=source)
    return {
        "panel_source": source,
        "synthetic_warning": _synthetic_notice(source),
        "winners": [r.name for r in out["winners"]],
        "results": [_result_dict(r) for r in out["all_results"]],
        "saved_csv": str(csv_path),
    }


# 便于 `python -m research_core.factor_lab.agent_gateway` 直接启动
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8710)
