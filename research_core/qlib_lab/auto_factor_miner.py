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

# Provider presets: name -> (base_url, env_key_for_api_key, default_model)
_PROVIDER_PRESETS: dict[str, tuple[str, str, str]] = {
    "openai":    ("https://api.openai.com/v1",       "OPENAI_API_KEY",      "gpt-4.1-mini"),
    "deepseek":  ("https://api.deepseek.com",        "DEEPSEEK_API_KEY",    "deepseek-chat"),
    "qwen":      ("https://dashscope.aliyuncs.com/compatible-mode/v1", "QWEN_API_KEY", "qwen-plus"),
    "zhipu":     ("https://open.bigmodel.cn/api/paas/v4", "ZHIPU_API_KEY",  "glm-4"),
    "moonshot":  ("https://api.moonshot.cn/v1",       "MOONSHOT_API_KEY",    "moonshot-v1-8k"),
    "custom":    ("",                                  "QFACTOR_API_KEY",     "gpt-4.1-mini"),
}


def _get_llm_config(provider: str) -> tuple[str, str, str]:
    """Resolve (base_url, api_key, model) for a provider.

    Resolution order:
      1. Provider preset from _PROVIDER_PRESETS
      2. Env var overrides: QFACTOR_BASE_URL, QFACTOR_API_KEY, QFACTOR_MODEL
      3. Fallback: OPENAI_API_KEY for backward compatibility
    """
    preset = _PROVIDER_PRESETS.get(provider)
    if preset is None:
        # Treat provider as a raw base_url
        base_url = provider
        api_key_env = "QFACTOR_API_KEY"
        default_model = "gpt-4.1-mini"
    else:
        base_url, api_key_env, default_model = preset

    # Env var overrides
    base_url = os.getenv("QFACTOR_BASE_URL", base_url)
    model = os.getenv("QFACTOR_MODEL", default_model)
    api_key = os.getenv("QFACTOR_API_KEY") or os.getenv(api_key_env) or os.getenv("OPENAI_API_KEY", "")

    return base_url, api_key, model


class AIFactorMiner:
    def __init__(self, factor_lab: QlibFactorLab):
        self.factor_lab = factor_lab

    def _build_prompt(self, theme: str, count: int, feedback: str = "") -> str:
        prompt = (
            "You are generating testable qlib factor expressions for A-share research.\n"
            "Return strict JSON as a list. Each element must include keys: "
            "name, expression, description, rationale, tags.\n"
            "Use qlib expression syntax and keep each expression concise.\n"
            "IMPORTANT: Use $close $open $high $low $volume $vwap (with $ prefix).\n"
            "Use Ref($close, 20) with positive lookback.  No negative offsets.\n"
            "Prefer time-series patterns: Ref, Mean, Std, Corr.\n"
            "Avoid: Rank, IndNeutralize, Group, Cut, custom functions.\n"
        )
        if feedback:
            prompt += f"\n=== Feedback from previous iteration ===\n{feedback}\n=== End feedback ===\n"
        prompt += f"\nResearch theme: {theme}\nNumber of candidates: {count}"
        return prompt

    def _parse_candidates(self, payload: str) -> list[FactorMiningCandidate]:
        # Strip markdown code fences (DeepSeek, Qwen, etc. wrap JSON in ```json ... ```)
        text = payload.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        try:
            raw = json.loads(text)
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

    def propose_candidates(
        self, theme: str, count: int = 5, feedback: str = "", provider: str = "openai",
    ) -> list[FactorMiningCandidate]:
        base_url, api_key, model = _get_llm_config(provider)
        if not api_key:
            return DEFAULT_EXPRESSIONS[:count]

        try:
            from openai import OpenAI
        except ImportError:
            return DEFAULT_EXPRESSIONS[:count]

        client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        prompt = self._build_prompt(theme, count, feedback=feedback)

        # Try chat completions first (works for DeepSeek, Qwen, Zhipu, etc.)
        # Fall back to responses API (OpenAI-specific)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            text = response.choices[0].message.content or ""
        except Exception:
            try:
                response = client.responses.create(model=model, input=prompt)
                text = getattr(response, "output_text", "") or ""
            except Exception:
                return DEFAULT_EXPRESSIONS[:count]

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
        feedback: str = "",
        provider: str = "openai",
    ) -> dict[str, Any]:
        proposals = self.propose_candidates(
            theme=theme, count=count, feedback=feedback, provider=provider,
        )
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
