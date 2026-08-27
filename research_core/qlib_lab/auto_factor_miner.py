from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

from contracts.factor import FactorMiningCandidate
from research_core.qlib_lab.factor_miner import QlibFactorLab


DEFAULT_EXPRESSIONS = [
    FactorMiningCandidate(
        name="short_term_reversal",
        expression="Ref($close, 5) / $close - 1",
        description="Short-term reversal factor based on 5-day mean reversion.",
        rationale="Prices that moved too far in the previous week may partially revert.",
        tags=["reversal", "price"],
    ),
    FactorMiningCandidate(
        name="volume_price_momentum",
        expression="($close / Ref($close, 20) - 1) * Log($volume / Ref($volume, 20))",
        description="Combines medium-term price momentum with abnormal trading activity.",
        rationale="Momentum reinforced by volume shocks tends to carry more information.",
        tags=["momentum", "volume"],
    ),
    FactorMiningCandidate(
        name="intraday_amplitude_pressure",
        expression="(($high - $low) / $close) * ($close / Ref($close, 10) - 1)",
        description="Measures whether expanding amplitude confirms the recent price trend.",
        rationale="High amplitude with aligned trend can indicate persistent positioning pressure.",
        tags=["volatility", "momentum"],
    ),
]


class AIFactorMiner:
    def __init__(self, factor_lab: QlibFactorLab):
        self.factor_lab = factor_lab

    def _build_prompt(self, theme: str, count: int) -> str:
        return (
            "You are generating testable qlib factor expressions for A-share research.\n"
            "Return strict JSON as a list. Each element must include keys: "
            "name, expression, description, rationale, tags.\n"
            "Use qlib expression syntax and keep each expression concise.\n"
            f"Research theme: {theme}\n"
            f"Number of candidates: {count}\n"
            "Avoid duplicate factors and avoid unsupported custom functions."
        )

    def _parse_candidates(self, payload: str) -> list[FactorMiningCandidate]:
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError:
            return DEFAULT_EXPRESSIONS
        if not isinstance(raw, list):
            return DEFAULT_EXPRESSIONS

        candidates: list[FactorMiningCandidate] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            expression = str(item.get("expression", "")).strip()
            if not name or not expression:
                continue
            tags = item.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            candidates.append(
                FactorMiningCandidate(
                    name=name,
                    expression=expression,
                    description=str(item.get("description", "")).strip(),
                    rationale=str(item.get("rationale", "")).strip(),
                    tags=[str(tag) for tag in tags],
                    metadata={"generator": "llm"},
                )
            )
        return candidates or DEFAULT_EXPRESSIONS

    def propose_candidates(self, theme: str, count: int = 5) -> list[FactorMiningCandidate]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return DEFAULT_EXPRESSIONS[:count]

        try:
            from openai import OpenAI
        except ImportError:
            return DEFAULT_EXPRESSIONS[:count]

        model = os.getenv("QFACTOR_OPENAI_MODEL", "gpt-4.1-mini")
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model,
            input=self._build_prompt(theme, count),
        )
        text = getattr(response, "output_text", "") or ""
        return self._parse_candidates(text)[:count]

    def auto_mine(
        self,
        *,
        theme: str,
        start_time: str,
        end_time: str,
        horizon: int = 5,
        count: int = 5,
        author: str = "ai",
    ) -> dict[str, Any]:
        proposals = self.propose_candidates(theme=theme, count=count)
        results: list[dict[str, Any]] = []
        for candidate in proposals:
            result = self.factor_lab.mine_expression(
                name=candidate.name,
                expression=candidate.expression,
                description=candidate.description or candidate.rationale,
                start_time=start_time,
                end_time=end_time,
                horizon=horizon,
                source="ai",
                author=author,
                tags=candidate.tags,
            )
            result["candidate"] = asdict(candidate)
            results.append(result)

        ranked = sorted(
            results,
            key=lambda item: (
                item["top_metrics"].get("ic_mean", 0.0),
                item["top_metrics"].get("long_short_spread", 0.0),
            ),
            reverse=True,
        )
        return {
            "theme": theme,
            "generated_count": len(results),
            "results": ranked,
        }
