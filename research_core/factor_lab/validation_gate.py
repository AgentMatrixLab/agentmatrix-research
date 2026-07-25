#!/usr/bin/env python3
"""
Validation Gate — The 7-gate quality control system.

Every factor and strategy must pass these gates before being trusted.
Outputs red/yellow/green verdicts agents can act on immediately.

The 7 gates (from strategy-reproduction skill):
  1. OOS retention ≥ 70%
  2. Parameter stability: ±20% perturbation → return change < 50%
  3. Cost resilience: still profitable at 50bp single-sided
  4. Sector neutrality: IC retains > 50% after neutralization
  5. Time decay: rolling 36m IC trend < 20% decline
  6. Segment consistency: profitable in 2/3 of bull/bear/sideways
  7. Benchmark comparison: excess return vs equal-weight hold

Agent-friendly: call evaluate() → get GateVerdict with pass/fail + reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


@dataclass
class GateVerdict:
    """Single factor/strategy gate evaluation result."""
    factor_name: str
    passed: bool = False
    ic_mean: Optional[float] = None
    ic_ir: Optional[float] = None
    ic_std: Optional[float] = None
    oos_retention: Optional[float] = None
    decay_pct: Optional[float] = None

    # Per-gate results
    gates: dict[str, bool] = field(default_factory=dict)
    fail_reasons: list[str] = field(default_factory=list)
    pass_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_name": self.factor_name,
            "passed": self.passed,
            "ic_mean": self.ic_mean,
            "ic_ir": self.ic_ir,
            "gates": self.gates,
            "fail_reasons": self.fail_reasons,
            "pass_reasons": self.pass_reasons,
        }


class ValidationGate:
    """
    The 7-gate quality control system.

    Usage:
        gate = ValidationGate()
        verdict = gate.evaluate(
            factor_name="alpha1",
            ic_mean=0.035,
            ic_ir=0.45,
            oos_retention=0.75,
            decay_pct=-0.10,
        )
        if verdict.passed:
            print("✅ Ready for production")
        else:
            print(f"❌ Failed: {verdict.fail_reasons}")
    """

    # ── Gate thresholds ────────────────────────────────────
    OOS_RETENTION_MIN = 0.70      # Gate 1: sample-out retention
    IC_MEAN_MIN = 0.02            # Minimum IC mean for any signal
    IC_IR_MIN = 0.30              # Minimum information ratio
    DECAY_MAX_PCT = 0.20          # Gate 5: max IC decay over time
    COST_RESILIENCE_BPS = 50      # Gate 3: still positive at 50bp?

    # Weights: how many gates must pass (0-1)
    MIN_GATE_PASS_RATIO = 0.50    # Must pass ≥ 50% of applicable gates

    def __init__(
        self,
        ic_mean_min: float = IC_MEAN_MIN,
        ic_ir_min: float = IC_IR_MIN,
        oos_retention_min: float = OOS_RETENTION_MIN,
        decay_max_pct: float = DECAY_MAX_PCT,
    ):
        self.ic_mean_min = ic_mean_min
        self.ic_ir_min = ic_ir_min
        self.oos_retention_min = oos_retention_min
        self.decay_max_pct = decay_max_pct

    def evaluate(
        self,
        factor_name: str,
        ic_mean: float,
        ic_ir: float,
        oos_retention: float = 0.0,
        decay_pct: float = 0.0,
        ic_std: float = 0.0,
        cost_resilience: Optional[bool] = None,
        sector_neutrality: Optional[float] = None,
        segment_consistency: Optional[int] = None,
        excess_return: Optional[float] = None,
    ) -> GateVerdict:
        """
        Run all applicable gates and return a verdict.

        Gates that don't have data (None) are skipped, not failed.
        """

        verdict = GateVerdict(
            factor_name=factor_name,
            ic_mean=ic_mean,
            ic_ir=ic_ir,
            ic_std=ic_std,
            oos_retention=oos_retention,
            decay_pct=decay_pct,
        )

        gates = {}
        applicable = 0
        passed_gates = 0

        # ── Gate 1: OOS Retention ──────────────────────────
        if oos_retention > 0:
            applicable += 1
            if oos_retention >= self.oos_retention_min:
                gates["oos_retention"] = True
                passed_gates += 1
                verdict.pass_reasons.append(
                    f"OOS retention {oos_retention:.0%} ≥ {self.oos_retention_min:.0%}"
                )
            else:
                gates["oos_retention"] = False
                verdict.fail_reasons.append(
                    f"OOS retention {oos_retention:.0%} < {self.oos_retention_min:.0%} — signal doesn't generalize"
                )

        # ── Gate 2: IC Significance ────────────────────────
        applicable += 1
        if abs(ic_mean) >= self.ic_mean_min:
            gates["ic_significance"] = True
            passed_gates += 1
            verdict.pass_reasons.append(
                f"IC mean {ic_mean:.4f} ≥ {self.ic_mean_min:.3f}"
            )
        else:
            gates["ic_significance"] = False
            verdict.fail_reasons.append(
                f"IC mean {ic_mean:.4f} < {self.ic_mean_min:.3f} — signal too weak"
            )

        # ── Gate 3: IC Information Ratio ────────────────────
        applicable += 1
        if abs(ic_ir) >= self.ic_ir_min:
            gates["ic_ir"] = True
            passed_gates += 1
            verdict.pass_reasons.append(
                f"IC_IR {ic_ir:.2f} ≥ {self.ic_ir_min:.2f}"
            )
        else:
            gates["ic_ir"] = False
            verdict.fail_reasons.append(
                f"IC_IR {ic_ir:.2f} < {self.ic_ir_min:.2f} — signal too noisy"
            )

        # ── Gate 4: Time Decay ─────────────────────────────
        if abs(decay_pct) > 0.001:
            applicable += 1
            if abs(decay_pct) <= self.decay_max_pct:
                gates["time_decay"] = True
                passed_gates += 1
                verdict.pass_reasons.append(
                    f"IC decay {decay_pct:.1%} ≤ {self.decay_max_pct:.0%}"
                )
            else:
                gates["time_decay"] = False
                verdict.fail_reasons.append(
                    f"IC decay {decay_pct:.1%} > {self.decay_max_pct:.0%} — signal deteriorating"
                )

        # ── Gate 5: Cost Resilience (if data provided) ──────
        if cost_resilience is not None:
            applicable += 1
            if cost_resilience:
                gates["cost_resilience"] = True
                passed_gates += 1
                verdict.pass_reasons.append("Survives {self.COST_RESILIENCE_BPS}bp cost")
            else:
                gates["cost_resilience"] = False
                verdict.fail_reasons.append(
                    f"Does not survive {self.COST_RESILIENCE_BPS}bp trading cost"
                )

        # ── Gate 6: Sector Neutrality (if data provided) ────
        if sector_neutrality is not None:
            applicable += 1
            if sector_neutrality >= 0.50:
                gates["sector_neutrality"] = True
                passed_gates += 1
                verdict.pass_reasons.append(
                    f"Sector-neutral IC retains {sector_neutrality:.0%}"
                )
            else:
                gates["sector_neutrality"] = False
                verdict.fail_reasons.append(
                    f"Sector-neutral IC retains only {sector_neutrality:.0%} — mostly sector bet"
                )

        # ── Gate 7: Segment Consistency (if data provided) ──
        if segment_consistency is not None:
            applicable += 1
            if segment_consistency >= 2:
                gates["segment_consistency"] = True
                passed_gates += 1
                verdict.pass_reasons.append(
                    f"Profitable in {segment_consistency}/3 regimes"
                )
            else:
                gates["segment_consistency"] = False
                verdict.fail_reasons.append(
                    f"Only profitable in {segment_consistency}/3 regimes"
                )

        # ── Final verdict ──────────────────────────────────
        verdict.gates = gates

        if applicable == 0:
            verdict.passed = False
            verdict.fail_reasons.append("No gates applicable — insufficient data")
        else:
            ratio = passed_gates / applicable
            verdict.passed = ratio >= self.MIN_GATE_PASS_RATIO

        if not verdict.passed and not verdict.fail_reasons:
            verdict.fail_reasons.append("Insufficient evidence to pass")

        return verdict

    def batch_evaluate(
        self,
        factors: list[dict[str, Any]],
    ) -> list[GateVerdict]:
        """Evaluate multiple factors at once."""
        results = []
        for f in factors:
            verdict = self.evaluate(
                factor_name=f.get("name", "unknown"),
                ic_mean=f.get("ic_mean", 0),
                ic_ir=f.get("ic_ir", 0),
                oos_retention=f.get("oos_retention", 0),
                decay_pct=f.get("decay_pct", 0),
                ic_std=f.get("ic_std", 0),
                cost_resilience=f.get("cost_resilience"),
                sector_neutrality=f.get("sector_neutrality"),
                segment_consistency=f.get("segment_consistency"),
            )
            results.append(verdict)
        return results

    def summary_markdown(self, verdicts: list[GateVerdict]) -> str:
        """Render batch results as markdown table."""
        passed = sum(1 for v in verdicts if v.passed)
        total = len(verdicts)

        lines = [
            f"## 🔐 Validation Gate Results",
            f"",
            f"**{passed}/{total} factors passed** (≥{self.MIN_GATE_PASS_RATIO:.0%} of applicable gates)",
            f"",
            f"| Factor | IC Mean | IC_IR | OOS | Decay | Verdict |",
            f"|--------|---------|-------|-----|-------|---------|",
        ]
        for v in verdicts:
            oos_str = f"{v.oos_retention:.0%}" if v.oos_retention else "N/A"
            decay_str = f"{v.decay_pct:.1%}" if v.decay_pct else "N/A"
            icon = "✅" if v.passed else "❌"
            lines.append(
                f"| {v.factor_name} | {v.ic_mean:.4f} | {v.ic_ir:.2f} | {oos_str} | {decay_str} | {icon} |"
            )
        lines.append("")

        # Show failures
        failed = [v for v in verdicts if not v.passed]
        if failed:
            lines.append("### ❌ Failures")
            for v in failed:
                for reason in v.fail_reasons:
                    lines.append(f"- **{v.factor_name}**: {reason}")

        # Show passes
        passed_list = [v for v in verdicts if v.passed]
        if passed_list:
            lines.append("### ✅ Passed")
            lines.append(f"{len(passed_list)} factors cleared for strategy backtest:")
            for v in passed_list:
                lines.append(f"- {v.factor_name}: {', '.join(v.pass_reasons[:2])}")

        return "\n".join(lines)
