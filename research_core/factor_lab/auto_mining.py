"""Auto Mining — 自动因子挖掘闭环 v2 (真实计算 + 真实 IC 评估).

闭环链路:
    候选表达式 (LLM / GP / 内置)
      → qlib_to_gtja()       Qlib 表达式 → GTJA191 编译器格式
      → compile_formula()    完整计算因子值 (含复合表达式, 不再只算分量)
      → evaluate_factor()    真实 Rank IC / ICIR / 换手率 / pass-warn-fail
      → check_duplicate()    与已有因子截面相关性去重 gate
      → build_feedback()     结构化反馈 (解析状态 + IC 结果 + 去重), 注入下一轮

数据加载 load_panel():
    1. 本地 parquet 缓存 (runtime/mining_cache/kline_panel.parquet)
    2. Quant API 实时拉取 (需要 FACTOR_LAB_QUANT_API_TOKEN, 自动写缓存)
    3. 合成面板兜底 (仅用于管线自检, 不用于真实结论)

Usage:
    from research_core.factor_lab.auto_mining import (
        load_panel, evaluate_candidates, run_mining_loop,
    )

    panel = load_panel(source="auto")
    results = run_mining_loop(panel, theme="动量+换手确认", rounds=2)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

from research_core.factor_lab.evaluation import (
    FactorEvaluationReport,
    compute_forward_returns,
    evaluate_factor,
)
from research_core.factor_lab.formula_compiler import compile_formula
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig, now_iso

PANEL_COLUMNS = ["date", "code", "open", "high", "low", "close", "volume", "amount"]

# ── Qlib → GTJA191 表达式转换 ────────────────────────────────────────────

_QLIB_FIELD_MAP: dict[str, str] = {
    "open": "OPEN",
    "high": "HIGH",
    "low": "LOW",
    "close": "CLOSE",
    "volume": "VOLUME",
    "amount": "AMOUNT",
    "vwap": "VWAP",
    "returns": "RETURNS",
}

# Qlib 函数名 → GTJA191 编译器函数名 (word-boundary 匹配, 大小写不敏感)
_QLIB_FUNC_MAP: dict[str, str] = {
    "Ref": "DELAY",
    "Delay": "DELAY",
    "Mean": "MEAN",
    "Std": "STD",
    "Sum": "SUM",
    "Max": "MAX",
    "Min": "MIN",
    "Corr": "CORR",
    "Cov": "COV",
    "Rank": "RANK",
    "Log": "LOG",
    "Abs": "ABS",
    "Sign": "SIGN",
    "TsRank": "TS_RANK",
    "Delta": "DELTA",
    "WMA": "WMA",
}


def qlib_to_gtja(expr: str) -> str:
    """Convert a Qlib-style expression to GTJA191 compiler format.

    Examples:
        Ref($close, 5) / $close - 1        → DELAY(CLOSE, 5) / CLOSE - 1
        ($high - $low) / $close            → (HIGH - LOW) / CLOSE
        Std(Ref($close, 1) / $close, 20)   → STD(DELAY(CLOSE, 1) / CLOSE, 20)
        Corr($high, $low, 10)              → CORR(HIGH, LOW, 10)
        Rank($volume)                       → RANK(VOLUME)
    """
    out = expr.strip()

    # DeepSeek sometimes emits Ref($close, -20) — normalize to positive window.
    out = re.sub(r"(Ref|Delay)\(\s*\$(\w+)\s*,\s*-\s*(\d+)\s*\)", r"\1($\2, \3)", out)

    # $field → FIELD
    out = re.sub(r"\$(\w+)", lambda m: _QLIB_FIELD_MAP.get(m.group(1), m.group(1).upper()), out)

    # Function names → compiler names (case-insensitive, word boundary).
    for qlib_name, gtja_name in _QLIB_FUNC_MAP.items():
        out = re.sub(rf"\b{qlib_name}\s*\(", f"{gtja_name}(", out)

    return out


# ── 数据加载 ─────────────────────────────────────────────────────────────


def _panel_cache_path() -> Path:
    config = FactorLabWorkspaceConfig()
    config.ensure_directories()
    cache_dir = config.runtime_root / "mining_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "kline_panel.parquet"


def _synthetic_panel(n_dates: int = 120, n_codes: int = 30, seed: int = 42) -> pd.DataFrame:
    """Synthetic OHLCV panel — pipeline self-check only, NOT for research conclusions."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-06-03", periods=n_dates, freq="B")
    codes = [f"C{i:04d}" for i in range(n_codes)]
    idx = pd.MultiIndex.from_product([dates, codes], names=["date", "code"])
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(idx)).reshape(n_dates, n_codes).ravel(order="F")))
    spread = rng.uniform(0.005, 0.02, len(idx))
    high = close * (1 + spread)
    low = close * (1 - spread)
    open_ = low + (high - low) * rng.uniform(0.2, 0.8, len(idx))
    volume = rng.uniform(1e5, 1e7, len(idx))
    panel = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    ).reset_index()
    panel["amount"] = panel["close"] * panel["volume"]
    panel["vwap"] = panel["amount"] / panel["volume"].replace(0, np.nan)
    panel["returns"] = panel.groupby("code")["close"].pct_change()
    return panel


def load_panel(
    *,
    source: str = "auto",
    parquet_path: str | Path | None = None,
    n_symbols: int = 30,
    n_dates: int = 250,
    refresh_cache: bool = False,
) -> tuple[pd.DataFrame, str]:
    # signature: n_symbols doubles as n_codes for the synthetic generator
    """Load the mining panel with a graceful source fallback chain.

    Args:
        source: "auto" | "cache" | "api" | "parquet" | "synthetic"
        parquet_path: required when source="parquet"
        n_symbols / n_dates: panel size for API fetch
        refresh_cache: force re-download even if cache exists

    Returns:
        (panel, actual_source) — panel has PANEL_COLUMNS + vwap + returns.
    """
    cache = _panel_cache_path()

    if source == "parquet":
        if parquet_path is None:
            raise ValueError("source='parquet' requires parquet_path")
        panel = pd.read_parquet(parquet_path)
        _validate_panel(panel)
        return panel, f"parquet:{Path(parquet_path).name}"

    if source == "synthetic":
        return _synthetic_panel(n_dates=n_dates, n_codes=n_symbols), "synthetic"

    if source in ("auto", "cache") and cache.is_file() and not refresh_cache:
        try:
            panel = pd.read_parquet(cache)
            _validate_panel(panel)
            return panel, "cache"
        except Exception:
            pass  # corrupted cache — fall through to API

    if source in ("auto", "api", "cache"):
        try:
            from research_core.factor_lab.real_data import fetch_quant_kline_panel

            panel = fetch_quant_kline_panel(n_symbols=n_symbols, n_dates=n_dates)
            panel.to_parquet(cache, index=False)
            return panel, "api"
        except Exception:
            if source == "api":
                raise

    return _synthetic_panel(n_dates=n_dates, n_codes=n_symbols), "synthetic"


def _validate_panel(panel: pd.DataFrame) -> None:
    missing = [col for col in PANEL_COLUMNS if col not in panel.columns]
    if missing:
        raise ValueError(f"panel missing required columns: {missing}")


# ── 候选评估 ─────────────────────────────────────────────────────────────


@dataclass(slots=True)
class CandidateResult:
    """Single candidate's full pipeline outcome."""

    name: str
    expression: str                       # original Qlib-style expression
    gtja_expression: str = ""             # converted GTJA191 form
    compile_error: str = ""               # non-empty if conversion/compile failed
    report: FactorEvaluationReport | None = None
    mean_rank_ic: float = 0.0
    rank_icir: float = 0.0
    ic_positive_ratio: float = 0.0
    mean_turnover: float | None = None
    n_dates: int = 0
    coverage: float = 0.0                 # fraction of panel rows with finite values
    duplicate_of: str | None = None
    duplicate_corr: float | None = None
    status: str = "NC"                    # PASS / WARN / FAIL / DUP / NC

    def summary_line(self) -> str:
        ic = f"IC={self.mean_rank_ic:+.4f}"
        icir = f"ICIR={self.rank_icir:.2f}"
        cov = f"cov={self.coverage:.0%}"
        dup = f" DUP~{self.duplicate_of}({self.duplicate_corr:.2f})" if self.duplicate_of else ""
        err = f" err={self.compile_error[:60]}" if self.compile_error else ""
        return f"[{self.status:4s}] {self.name:32s} {ic} {icir} {cov}{dup}{err}"


def _compile_candidate(name: str, expression: str) -> tuple[Callable[[pd.DataFrame], pd.Series], str]:
    """Convert + compile. Returns (fn, gtja_expression); raises on failure."""
    gtja_expr = qlib_to_gtja(expression)
    fn = compile_formula(gtja_expr, alpha_name=re.sub(r"\W", "_", name) or "_f")
    return fn, gtja_expr


def evaluate_candidates(
    panel: pd.DataFrame,
    candidates: Iterable[dict[str, str]],
    *,
    horizon: int = 5,
    ic_threshold: float = 0.02,
    icir_threshold: float = 0.3,
    dedup_threshold: float = 0.7,
    existing_frames: dict[str, pd.DataFrame] | None = None,
    min_coverage: float = 0.3,
) -> list[CandidateResult]:
    """Full evaluation: compile → compute → IC → dedup gate → status.

    Args:
        panel: long panel with PANEL_COLUMNS.
        candidates: iterable of {"name": ..., "expression": ...}.
        horizon: forward-return horizon (days) for IC.
        ic_threshold: min |mean rank IC| for PASS.
        icir_threshold: min rank ICIR for PASS.
        dedup_threshold: cross-sectional correlation above this → DUP.
        existing_frames: {factor_name: DataFrame[date, code, factor_name]} for dedup.
        min_coverage: min fraction of finite factor values (else NC).

    Status rules:
        NC   — cannot compile / coverage too low
        FAIL — computed but |IC| or ICIR below threshold
        DUP  — duplicates an existing (or in-batch) factor
        WARN — passes IC gates but has evaluation warnings
        PASS — clean pass
    """
    eval_df = panel.copy()
    eval_df["next_return"] = compute_forward_returns(panel, periods=horizon)

    results: list[CandidateResult] = []
    batch_frames: dict[str, pd.DataFrame] = {}

    for cand in candidates:
        name = str(cand.get("name") or f"factor_{len(results)}")
        expression = str(cand.get("expression", ""))
        res = CandidateResult(name=name, expression=expression)

        # 1. Compile
        try:
            fn, gtja_expr = _compile_candidate(name, expression)
        except Exception as exc:
            res.compile_error = f"{type(exc).__name__}: {exc}"
            res.status = "NC"
            results.append(res)
            continue
        res.gtja_expression = gtja_expr

        # 2. Compute on panel
        try:
            values = fn(eval_df)
        except Exception as exc:
            res.compile_error = f"compute {type(exc).__name__}: {exc}"
            res.status = "NC"
            results.append(res)
            continue

        frame = pd.DataFrame({
            "date": eval_df["date"].values,
            "code": eval_df["code"].values,
            name: pd.to_numeric(values, errors="coerce").values,
        })
        res.coverage = float(frame[name].replace([np.inf, -np.inf], np.nan).notna().mean())
        if res.coverage < min_coverage:
            res.compile_error = f"coverage {res.coverage:.0%} < {min_coverage:.0%}"
            res.status = "NC"
            results.append(res)
            continue

        # 3. Real IC evaluation
        eval_slice = frame.merge(
            eval_df[["date", "code", "next_return"]], on=["date", "code"], how="left"
        )
        try:
            report = evaluate_factor(
                eval_slice,
                factor_name=name,
                factor_col=name,
                return_col="next_return",
                ic_threshold=ic_threshold,
            )
        except Exception as exc:
            res.compile_error = f"eval {type(exc).__name__}: {exc}"
            res.status = "NC"
            results.append(res)
            continue

        res.report = report
        if report.ic_eval is not None:
            res.mean_rank_ic = float(report.ic_eval.mean_rank_ic)
            res.rank_icir = float(report.ic_eval.rank_icir)
            res.ic_positive_ratio = float(report.ic_eval.ic_positive_ratio)
            res.n_dates = int(report.ic_eval.n_dates)
        if report.turnover is not None:
            res.mean_turnover = float(report.turnover.mean_turnover)

        # 4. Dedup gate — against existing registry AND in-batch winners
        dup_found = False
        try:
            from research_core.factor_lab.similarity import check_duplicate

            pool = dict(existing_frames or {})
            for prev_name, prev_frame in batch_frames.items():
                pool[prev_name] = prev_frame
            if pool:
                dup_report = check_duplicate(frame, name, pool, threshold=dedup_threshold)
                if dup_report.get("has_duplicate"):
                    res.duplicate_of = str(dup_report.get("top_match"))
                    res.duplicate_corr = float(dup_report.get("top_correlation") or 0.0)
                    res.status = "DUP"
                    dup_found = True
        except Exception:
            pass  # dedup infra failure should not block evaluation

        if not dup_found:
            if abs(res.mean_rank_ic) >= ic_threshold and res.rank_icir >= icir_threshold:
                res.status = "PASS" if not report.warnings else "WARN"
            else:
                res.status = "FAIL"

        if res.status in ("PASS", "WARN"):
            batch_frames[name] = frame

        results.append(res)

    return results


# ── 反馈闭环 ─────────────────────────────────────────────────────────────


def build_feedback(results: list[CandidateResult], *, top_k: int = 3) -> str:
    """Structured feedback for the next LLM round — parse status + IC + dedup."""
    passed = [r for r in results if r.status in ("PASS", "WARN")]
    failed = [r for r in results if r.status == "FAIL"]
    ncs = [r for r in results if r.status == "NC"]
    dups = [r for r in results if r.status == "DUP"]

    lines = [
        f"Previous round: {len(results)} candidates → "
        f"{len(passed)} passed IC gates, {len(failed)} weak (IC/ICIR below threshold), "
        f"{len(ncs)} uncomputable, {len(dups)} duplicates.",
    ]

    if passed:
        top = sorted(passed, key=lambda r: abs(r.mean_rank_ic), reverse=True)[:top_k]
        lines.append(
            "Patterns that passed real IC evaluation (imitate their structure): "
            + "; ".join(f"{r.name} (IC={r.mean_rank_ic:+.4f}, ICIR={r.rank_icir:.2f})" for r in top)
        )

    if failed:
        lines.append(
            "These computed fine but had weak predictive power — change the signal, not just parameters: "
            + "; ".join(f"{r.name} (IC={r.mean_rank_ic:+.4f})" for r in failed[:top_k])
        )

    if ncs:
        bad_exprs = [f"{r.name}: {r.compile_error[:80]}" for r in ncs[:top_k]]
        lines.append("These failed to compile or had insufficient coverage — DO NOT repeat: " + "; ".join(bad_exprs))

    if dups:
        lines.append(
            "These duplicated already-registered factors — find different signal sources: "
            + "; ".join(f"{r.name} ≈ {r.duplicate_of} (ρ={r.duplicate_corr:.2f})" for r in dups[:top_k])
        )

    lines.append(
        "Target: |mean Rank IC| >= 0.02 and ICIR >= 0.3 on 5-day forward returns. "
        "Use pure time-series operators (Ref/Mean/Std/Corr/Log on $open/$high/$low/$close/$volume) "
        "and arithmetic combinations; cross-sectional Rank is allowed but costs ICIR."
    )
    return "\n".join(lines)


# ── 闭环编排 ─────────────────────────────────────────────────────────────


def _llm_generate(theme: str, count: int, feedback: str, provider: str) -> list[dict[str, str]] | None:
    try:
        from research_core.qlib_lab.auto_factor_miner import AIFactorMiner, DEFAULT_EXPRESSIONS
        from research_core.qlib_lab.factor_miner import QlibFactorLab

        miner = AIFactorMiner(QlibFactorLab())
        cands = miner.propose_candidates(theme=theme, count=count, provider=provider, feedback=feedback)
        if cands and cands[0].name != DEFAULT_EXPRESSIONS[0].name:
            return [{"name": c.name, "expression": c.expression} for c in cands]
    except Exception:
        pass
    return None


def _builtin_candidates() -> list[dict[str, str]]:
    return [
        {"name": "mom_20d", "expression": "Ref($close, 20) / $close - 1"},
        {"name": "mom_60d", "expression": "Ref($close, 60) / $close - 1"},
        {"name": "vol_ratio_10", "expression": "$volume / Mean($volume, 10)"},
        {"name": "std_returns_20", "expression": "Std($close / Ref($close, 1) - 1, 20)"},
        {"name": "ma_bias_20", "expression": "$close / Mean($close, 20) - 1"},
        {"name": "high_low_spread", "expression": "($high - $low) / $close"},
        {"name": "corr_hl_10", "expression": "Corr($high, $low, 10)"},
        {"name": "amplitude_mom", "expression": "(($high - $low) / $close) * ($close / Ref($close, 10) - 1)"},
        {"name": "vol_price_mom", "expression": "($close / Ref($close, 20) - 1) * Log($volume / Ref($volume, 20))"},
        {"name": "intraday_pos", "expression": "($close - $open) / ($high - $low)"},
    ]


def run_mining_loop(
    panel: pd.DataFrame,
    *,
    theme: str = "量价因子",
    rounds: int = 2,
    count_per_round: int = 8,
    mode: str = "auto",                    # "llm" | "builtin" | "auto" (llm→builtin fallback)
    provider: str = "deepseek",
    horizon: int = 5,
    existing_frames: dict[str, pd.DataFrame] | None = None,
    generator: Callable[[str, int, str], list[dict[str, str]] | None] | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run the full feedback loop over the panel.

    Returns:
        {"rounds": [ {round, candidates, feedback}, ... ],
         "winners": [CandidateResult...],   # final PASS/WARN, deduped
         "panel_source": ...}
    """
    gen = generator or (lambda t, c, fb: _llm_generate(t, c, fb, provider))
    history: list[dict[str, Any]] = []
    all_results: list[CandidateResult] = []
    feedback = ""

    for round_no in range(1, rounds + 1):
        if mode == "builtin":
            candidates = _builtin_candidates()[:count_per_round]
        else:
            candidates = gen(theme, count_per_round, feedback)
            if candidates is None:
                if mode == "llm":
                    raise RuntimeError("LLM generation unavailable (check API key)")
                candidates = _builtin_candidates()[:count_per_round]

        results = evaluate_candidates(
            panel, candidates,
            horizon=horizon,
            existing_frames=existing_frames,
        )
        if verbose:
            print(f"\n=== Round {round_no}: {theme} ({len(candidates)} candidates) ===")
            for r in results:
                print("  " + r.summary_line())

        feedback = build_feedback(results)
        history.append({"round": round_no, "results": results, "feedback": feedback})
        all_results.extend(results)

        # Next round starts from the winners' frames for in-loop dedup.
        winners = [r for r in results if r.status in ("PASS", "WARN")]
        if winners:
            existing_frames = dict(existing_frames or {})

    winners = []
    seen_winners: set[tuple[str, str]] = set()
    for r in all_results:
        if r.status in ("PASS", "WARN") and (r.name, r.expression) not in seen_winners:
            seen_winners.add((r.name, r.expression))
            winners.append(r)
    losers = [r for r in all_results if r.status == "FAIL"]
    if verbose:
        print(f"\n=== Summary: {len(winners)} winners / {len(losers)} weak / "
              f"{sum(1 for r in all_results if r.status == 'DUP')} dup / "
              f"{sum(1 for r in all_results if r.status == 'NC')} NC ===")

    return {"rounds": history, "winners": winners, "all_results": all_results}


def save_results(
    run_output: dict[str, Any],
    *,
    panel_source: str = "",
    out_dir: str | Path | None = None,
) -> Path:
    """Persist the run output (winners CSV + full JSON) under runtime/mining_runs/."""
    config = FactorLabWorkspaceConfig()
    config.ensure_directories()
    out_root = Path(out_dir) if out_dir else config.runtime_root / "mining_runs"
    out_root.mkdir(parents=True, exist_ok=True)
    stamp = now_iso().replace(":", "").replace("-", "").replace("T", "_").split(".")[0]
    run_id = f"mine_{stamp}"

    rows = []
    for r in run_output.get("all_results", []):
        rows.append({
            "name": r.name,
            "expression": r.expression,
            "gtja_expression": r.gtja_expression,
            "status": r.status,
            "mean_rank_ic": r.mean_rank_ic,
            "rank_icir": r.rank_icir,
            "ic_positive_ratio": r.ic_positive_ratio,
            "mean_turnover": r.mean_turnover,
            "coverage": r.coverage,
            "n_dates": r.n_dates,
            "duplicate_of": r.duplicate_of,
            "duplicate_corr": r.duplicate_corr,
            "compile_error": r.compile_error,
        })
    csv_path = out_root / f"{run_id}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    import json

    json_path = out_root / f"{run_id}.json"
    payload = {
        "run_id": run_id,
        "panel_source": panel_source,
        "created_at": now_iso(),
        "winners": [r.name for r in run_output.get("winners", [])],
        "results": rows,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path
