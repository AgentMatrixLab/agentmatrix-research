"""Daily factor mining loop for AGE-8.

Runs every day on freshly updated data: compute candidate factors on the latest
window, evaluate IC / ICIR / turnover, dedupe against the registered library,
and gate new factors into the registry.

v1 candidate universe: Alpha158 first-20 (price/volume technicals).
Later iterations (Ada): full Alpha158 + qlib_lab AIFactorMiner + news-driven
candidates wired through the same gates.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from common.paths import runtime_path
from research_core.alpha158_lab.factors.compute import compute_alpha158_factors
from research_core.alpha158_lab.factors.specs import ALPHA158_FIRST_10, ALPHA158_SECOND_10
from research_core.daily_automation.store import DailyStore
from research_core.factor_lab.evaluation import evaluate_factor

DEFAULT_BATCH = tuple(ALPHA158_FIRST_10 + ALPHA158_SECOND_10)
REGISTRY_PATH = runtime_path("factor_registry.json")
MINING_LOG_PATH = runtime_path("daily_mining_log.jsonl")

# Gate thresholds (per factor-investing-methodology: IC_IR > 0.5 promising, keep v1 looser but sane)
IC_THRESHOLD = 0.03
ICIR_THRESHOLD = 0.30
CORR_THRESHOLD = 0.70  # reject candidates that duplicate an already-registered factor


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_registry(path: Path = REGISTRY_PATH) -> list[dict[str, Any]]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("factors", []) if isinstance(data, dict) else []
        except json.JSONDecodeError:
            return []
    return []


def _save_registry(factors: list[dict[str, Any]], path: Path = REGISTRY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"factors": factors, "updated": _now_iso()}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_mining_log(record: dict[str, Any], path: Path = MINING_LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _factor_correlation_matrix(
    factor_frame: pd.DataFrame,
    names: list[str],
) -> pd.DataFrame:
    """Average cross-sectional rank correlation per date between factor pairs."""
    data = factor_frame.copy()
    data["date"] = pd.to_datetime(data["date"])
    corrs: dict[tuple[str, str], list[float]] = {}
    for _, daily in data.groupby("date"):
        if len(daily) < 10:
            continue
        ranks = daily[names].rank()
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                c = ranks[a].corr(ranks[b])
                if pd.notna(c):
                    corrs.setdefault((a, b), []).append(float(c))
    pairs = {frozenset(k): k for k in corrs}
    mat = pd.DataFrame(np.nan, index=names, columns=names)
    np.fill_diagonal(mat.values, 1.0)
    for (a, b), vals in corrs.items():
        mean_c = float(np.mean(vals)) if vals else np.nan
        mat.loc[a, b] = mean_c
        mat.loc[b, a] = mean_c
    return mat


class DailyFactorMiner:
    def __init__(
        self,
        store: DailyStore,
        *,
        registry_path: Path = REGISTRY_PATH,
        batch: tuple[str, ...] | None = None,
        ic_threshold: float = IC_THRESHOLD,
        icir_threshold: float = ICIR_THRESHOLD,
        corr_threshold: float = CORR_THRESHOLD,
    ) -> None:
        self.store = store
        self.registry_path = Path(registry_path)
        self.batch = list(batch or DEFAULT_BATCH)
        self.ic_threshold = ic_threshold
        self.icir_threshold = icir_threshold
        self.corr_threshold = corr_threshold

    # ------------------------------------------------------------------
    def run(self, end_date: str, lookback_days: int = 90) -> dict[str, Any]:
        end_ts = pd.Timestamp(end_date)
        start_ts = end_ts - pd.Timedelta(days=int(lookback_days * 1.6))
        panel = self.store.load_panel(
            start=start_ts.strftime("%Y-%m-%d"),
            end=end_ts.strftime("%Y-%m-%d"),
        )
        if len(panel) < 200 or panel["code"].nunique() < 20:
            return {
                "status": "skipped",
                "reason": f"insufficient panel data ({len(panel)} rows, {panel['code'].nunique() if len(panel) else 0} codes)",
                "end_date": end_date,
            }

        panel = panel.sort_values(["code", "date"]).copy()
        panel["next_return"] = panel.groupby("code")["close"].shift(-1) / panel["close"] - 1
        panel = panel[panel["next_return"].notna()]

        factor_frame = compute_alpha158_factors(panel, factor_names=self.batch)
        merged = factor_frame.merge(
            panel[["date", "code", "next_return"]],
            on=["date", "code"],
            how="inner",
        )

        registry = _load_registry(self.registry_path)
        registered_names = {f["name"] for f in registry}

        results: list[dict[str, Any]] = []
        gated: list[dict[str, Any]] = []
        duplicates: list[dict[str, Any]] = []
        for name in self.batch:
            long = merged[["date", "code", name, "next_return"]].rename(
                columns={name: "factor_value"}
            )
            long = long.dropna(subset=["factor_value", "next_return"])
            if len(long) < 200:
                continue
            report = evaluate_factor(
                long,
                factor_name=name,
                factor_col="factor_value",
                return_col="next_return",
            )
            ic = float(report.ic_eval.mean_rank_ic)
            icir = float(report.ic_eval.rank_icir)
            turnover = float(report.turnover.mean_turnover)
            row = {
                "name": name,
                "source": "alpha158",
                "ic": round(ic, 4),
                "icir": round(icir, 3),
                "turnover": round(turnover, 3),
                "status": report.status,
                "already_registered": name in registered_names,
            }
            results.append(row)

            if abs(ic) >= self.ic_threshold and icir >= self.icir_threshold and report.status != "fail":
                if name in registered_names:
                    duplicates.append(row)
                    continue
                gated.append(row)

        # correlation gate for newly gated candidates vs registered factors
        corr_mat = _factor_correlation_matrix(factor_frame, self.batch)
        new_factors: list[dict[str, Any]] = []
        for row in gated:
            row["corr_max"] = 0.0
            max_corr, with_name = 0.0, ""
            for other in registered_names:
                if other in corr_mat.columns and other != row["name"]:
                    c = float(corr_mat.loc[row["name"], other])
                    if pd.notna(c) and abs(c) > max_corr:
                        max_corr, with_name = abs(c), other
            row["corr_max"] = round(max_corr, 3)
            row["corr_with"] = with_name
            if max_corr < self.corr_threshold:
                new_factors.append(row)

        if new_factors:
            for row in new_factors:
                registry.append(
                    {
                        "name": row["name"],
                        "source": row["source"],
                        "added": _now_iso(),
                        "ic": row["ic"],
                        "icir": row["icir"],
                        "turnover": row["turnover"],
                        "corr_max": row["corr_max"],
                        "status": row["status"],
                        "batch": "alpha158_first20",
                    }
                )
            _save_registry(registry, self.registry_path)

        summary = {
            "status": "ok",
            "end_date": end_date,
            "lookback_days": lookback_days,
            "panel_rows": len(merged),
            "panel_codes": int(merged["code"].nunique()),
            "evaluated": len(results),
            "gated": len(gated),
            "new_registered": len(new_factors),
            "duplicates_rejected": len(duplicates),
            "results": sorted(results, key=lambda r: -abs(r["ic"])),
            "new_factors": new_factors,
            "as_of": _now_iso(),
        }
        _append_mining_log({**summary, "results": None, "new_factors": None})
        return summary
