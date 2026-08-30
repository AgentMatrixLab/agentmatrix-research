"""GP Factor Search — 遗传规划自动因子搜索.

在 auto_mining 的真实评估管线 (compile → compute → IC → dedup) 之上实现
遗传规划 (Genetic Programming):
    1. 随机表达式树种群 (Qlib 语法, 直接走 qlib_to_gtja 桥接)
    2. fitness = |mean rank IC| × sqrt(ICIR 截断) − 相似度惩罚
    3. 锦标赛选择 + 子树交叉 + 变异
    4. 精英保留, 每代输出 top-N

用法:
    from research_core.factor_lab.gp_search import GPFactorMiner
    miner = GPFactorMiner(panel)
    winners = miner.evolve(generations=5, population=24)
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from research_core.factor_lab.auto_mining import CandidateResult, evaluate_candidates

# ── 表达式树 ─────────────────────────────────────────────────────────────

FIELDS = ["$open", "$high", "$low", "$close", "$volume"]
WINDOWS = [3, 5, 10, 20, 30, 60]

# (模板, 系列参数个数) — 窗口参数在生成时填充
TEMPLATES: list[tuple[str, int]] = [
    ("Ref({s}, {w}) / {s} - 1", 1),                    # 动量
    ("{s} / Mean({s}, {w}) - 1", 1),                    # 均值偏离
    ("Std({s} / Ref({s}, 1) - 1, {w})", 1),             # 波动率
    ("$volume / Mean($volume, {w})", 1),                 # 量比
    ("($high - $low) / {s}", 1),                        # 振幅
    ("({a} - $open) / ($high - $low)", 2),              # 日内位置
    ("Corr({a}, {b}, {w})", 2),                         # 滚动相关
    ("({s} - Ref({s}, {w})) / Ref({s}, {w})", 1),       # 变化率
    ("Log({s} / Ref({s}, {w}))", 1),                    # 对数收益
    ("Mean({s}, {w1}) / Mean({s}, {w2}) - 1", 1),       # 双均线
]


# 简化实现: 直接生成字符串表达式 (树操作在字符串层面做子树交换)


def _random_leaf(rng: random.Random) -> str:
    template, _ = rng.choice(TEMPLATES)
    f = rng.choice(FIELDS)
    w = rng.choice(WINDOWS)
    if template == "Corr({a}, {b}, {w})":
        a, b = rng.choice(FIELDS), rng.choice(FIELDS)
        return template.format(a=a, b=b, w=w)
    if "({a}" in template:
        return template.format(a=f, b=f, w=w)
    if "{w1}" in template:
        w1, w2 = sorted(rng.sample(WINDOWS, 2))
        return template.format(s=f, w1=w1, w2=w2)
    return template.format(s=f, w=w)


def random_expression(rng: random.Random, max_depth: int = 2) -> str:
    if max_depth <= 0 or rng.random() < 0.7:
        return _random_leaf(rng)
    left = random_expression(rng, max_depth - 1)
    right = random_expression(rng, max_depth - 1)
    op = rng.choice(["+", "-", "*", "/"])
    return f"({left} {op} {right})"


def _split_top_level(expr: str) -> list[str]:
    """按顶层二元运算符切分子表达式 (忽略括号内)."""
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and ch in "+-*/" and not (ch in "*/" and i == start):
            # 跳过一元负号 (如 "-1 *" 开头)
            if ch in "+-" and i == start:
                continue
            parts.append(expr[start:i].strip())
            start = i + 1
    parts.append(expr[start:].strip())
    return parts


def mutate_expression(expr: str, rng: random.Random) -> str:
    """变异: 随机替换一个窗口数字 / 字段 / 子表达式."""
    choice = rng.random()
    if choice < 0.4:
        # 变窗口
        nums = [(m.start(), m.end()) for m in __import__("re").finditer(r"\b(3|5|10|20|30|60)\b", expr)]
        if nums:
            s, e = rng.choice(nums)
            new_w = rng.choice([w for w in WINDOWS if str(w) != expr[s:e]])
            return expr[:s] + str(new_w) + expr[e:]
    if choice < 0.7:
        # 变字段
        import re as _re

        fields = list(_re.finditer(r"\$(open|high|low|close|volume)", expr))
        if fields:
            m = rng.choice(fields)
            new_f = rng.choice([f for f in FIELDS if f != m.group(0)])
            return expr[: m.start()] + new_f + expr[m.end() :]
    # 整个子表达式重生成
    parts = _split_top_level(expr)
    if len(parts) >= 2:
        idx = rng.randrange(len(parts))
        parts[idx] = random_expression(rng, max_depth=1)
        # 用原运算符拼回去 — 简化: 重新组合
        return _join_parts(parts)
    return random_expression(rng, max_depth=2)


def _join_parts(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    left = parts[0]
    for p in parts[1:]:
        left = f"({left} / {p})"
    return left


def crossover(a: str, b: str, rng: random.Random) -> str:
    """交叉: 把 a 的一个顶层子表达式替换为 b 的一个顶层子表达式."""
    parts_a = _split_top_level(a)
    parts_b = _split_top_level(b)
    if len(parts_a) < 2 or len(parts_b) < 1:
        return a
    idx = rng.randrange(len(parts_a))
    donor = rng.choice(parts_b)
    parts_a[idx] = donor.strip("()")
    return _join_parts(parts_a)


# ── GP 主循环 ────────────────────────────────────────────────────────────


@dataclass(slots=True)
class GPRunConfig:
    population: int = 24
    generations: int = 5
    elite_frac: float = 0.25
    crossover_prob: float = 0.6
    mutation_prob: float = 0.35
    icir_floor: float = 0.05        # ICIR 截断, 防止微小 IC × 高 ICIR 的病态解
    seed: int = 7


class GPFactorMiner:
    """GP 搜索器 — 复用 auto_mining 的真实评估管线作为 fitness."""

    def __init__(
        self,
        panel: pd.DataFrame,
        *,
        horizon: int = 5,
        existing_frames: dict[str, pd.DataFrame] | None = None,
    ) -> None:
        self.panel = panel
        self.horizon = horizon
        self.existing_frames = existing_frames or {}
        self.cache: dict[str, CandidateResult] = {}
        self.eval_count = 0

    def _fitness(self, r: CandidateResult) -> float:
        if r.status in ("NC", "DUP"):
            return -1.0 if r.status == "NC" else -0.5
        icir = max(r.rank_icir, -r.rank_icir) if r.rank_icir < 0 else r.rank_icir
        # 方向统一的因子取绝对值; 负 IC 因子翻转即可用
        score = abs(r.mean_rank_ic) * min(abs(r.rank_icir), 3.0)
        if r.coverage < 0.5:
            score *= r.coverage * 2
        return score

    def _evaluate(self, exprs: list[str]) -> list[CandidateResult]:
        to_eval = [e for e in exprs if e not in self.cache]
        if to_eval:
            import hashlib

            cands = [
                {
                    "name": f"gp_{hashlib.md5(e.encode()).hexdigest()[:6]}",
                    "expression": e,
                }
                for e in to_eval
            ]
            results = evaluate_candidates(
                self.panel, cands,
                horizon=self.horizon,
                existing_frames=self.existing_frames,
            )
            for expr, res in zip(to_eval, results):
                self.cache[expr] = res
            self.eval_count += len(to_eval)
        return [self.cache[e] for e in exprs]

    def evolve(
        self,
        *,
        generations: int | None = None,
        population: int | None = None,
        verbose: bool = True,
        config: GPRunConfig | None = None,
    ) -> dict[str, Any]:
        cfg = config or GPRunConfig(
            generations=generations or 5,
            population=population or 24,
        )
        rng = random.Random(cfg.seed)
        n_pop = cfg.population

        # 初始种群
        exprs = list({random_expression(rng, max_depth=2) for _ in range(n_pop * 2)})[:n_pop]
        best_overall: list[tuple[float, str]] = []

        for gen in range(cfg.generations):
            results = self._evaluate(exprs)
            scored = sorted(
                ((self._fitness(r), expr) for expr, r in zip(exprs, results)),
                key=lambda x: x[0],
                reverse=True,
            )
            gen_best = scored[0]
            best_overall.extend(scored)
            if verbose:
                top3 = ", ".join(f"{s:.3f}" for s, _ in scored[:3])
                print(f"  gen {gen + 1}/{cfg.generations}: best={gen_best[0]:.3f} top3=[{top3}] evals={self.eval_count}")

            # 精英保留
            n_elite = max(1, int(n_pop * cfg.elite_frac))
            elites = [e for _, e in scored[:n_elite]]

            # 生成下一代
            next_gen: list[str] = list(elites)
            while len(next_gen) < n_pop:
                # 锦标赛选择
                t1 = max(rng.sample(scored, k=min(3, len(scored))))[1]
                t2 = max(rng.sample(scored, k=min(3, len(scored))))[1]
                if rng.random() < cfg.crossover_prob:
                    child = crossover(t1, t2, rng)
                else:
                    child = t1
                if rng.random() < cfg.mutation_prob:
                    child = mutate_expression(child, rng)
                if child not in next_gen:
                    next_gen.append(child)
            exprs = next_gen

        # 最终 top-N
        best_overall.sort(key=lambda x: x[0], reverse=True)
        seen: set[str] = set()
        top: list[tuple[float, str]] = []
        for score, expr in best_overall:
            if expr in seen:
                continue
            seen.add(expr)
            top.append((score, expr))
            if len(top) >= 10:
                break

        winners = [self.cache[e] for _, e in top if e in self.cache and self.cache[e].status in ("PASS", "WARN", "FAIL")]
        if verbose:
            print(f"\n  GP done: {self.eval_count} evaluations, {len(winners)} candidates in final pool")
        return {"top": top, "winners": winners, "evaluations": self.eval_count}
