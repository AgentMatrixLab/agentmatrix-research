#!/usr/bin/env python3
"""Tests for agent_pipeline and validation_gate modules."""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research_core.factor_lab.validation_gate import ValidationGate, GateVerdict


def test_gate_all_pass():
    """A strong factor should pass all gates."""
    gate = ValidationGate()
    verdict = gate.evaluate(
        factor_name="alpha_strong",
        ic_mean=0.045,
        ic_ir=0.65,
        oos_retention=0.82,
        decay_pct=-0.05,
    )
    assert verdict.passed, f"Expected pass, got: {verdict.fail_reasons}"
    assert verdict.ic_mean == 0.045
    assert len(verdict.pass_reasons) >= 3


def test_gate_all_fail():
    """A weak factor should fail."""
    gate = ValidationGate()
    verdict = gate.evaluate(
        factor_name="alpha_weak",
        ic_mean=0.005,
        ic_ir=0.10,
        oos_retention=0.30,
        decay_pct=-0.50,
    )
    assert not verdict.passed, "Expected fail for weak factor"
    assert len(verdict.fail_reasons) >= 2


def test_gate_borderline():
    """A borderline factor should be correctly classified."""
    gate = ValidationGate()
    # Passes IC mean and OOS but fails IC_IR and decay
    verdict = gate.evaluate(
        factor_name="alpha_borderline",
        ic_mean=0.025,
        ic_ir=0.25,
        oos_retention=0.75,
        decay_pct=-0.30,
    )
    # 2/4 gates pass = 50% → passes (≥50% threshold)
    assert verdict.passed


def test_gate_missing_data():
    """Missing optional gates should not count as failures."""
    gate = ValidationGate()
    verdict = gate.evaluate(
        factor_name="alpha_partial",
        ic_mean=0.040,
        ic_ir=0.55,
        # No OOS, no decay data
    )
    # Only IC significance + IC_IR applicable → 2/2 = 100%
    assert verdict.passed


def test_gate_cost_resilience():
    """Cost resilience gate should work when data provided."""
    gate = ValidationGate()
    verdict_pass = gate.evaluate(
        factor_name="alpha_cost_ok",
        ic_mean=0.035,
        ic_ir=0.50,
        cost_resilience=True,
    )
    assert verdict_pass.passed

    verdict_fail = gate.evaluate(
        factor_name="alpha_cost_bad",
        ic_mean=0.005,       # weak IC
        ic_ir=0.10,          # weak IR
        cost_resilience=False,
    )
    assert not verdict_fail.passed  # 0/3 fails


def test_gate_sector_neutrality():
    """Sector neutrality gate."""
    gate = ValidationGate()
    verdict = gate.evaluate(
        factor_name="alpha_sector",
        ic_mean=0.030,
        ic_ir=0.40,
        sector_neutrality=0.60,
    )
    assert verdict.passed


def test_gate_segment_consistency():
    """Segment consistency gate."""
    gate = ValidationGate()
    verdict = gate.evaluate(
        factor_name="alpha_segments",
        ic_mean=0.030,
        ic_ir=0.40,
        segment_consistency=2,  # 2/3 regimes
    )
    assert verdict.passed


def test_batch_evaluate():
    """Batch evaluation should handle multiple factors."""
    gate = ValidationGate()
    factors = [
        {"name": "f1", "ic_mean": 0.050, "ic_ir": 0.80, "oos_retention": 0.85},
        {"name": "f2", "ic_mean": 0.010, "ic_ir": 0.15, "oos_retention": 0.30},
        {"name": "f3", "ic_mean": 0.030, "ic_ir": 0.45, "oos_retention": 0.72},
    ]
    verdicts = gate.batch_evaluate(factors)
    assert len(verdicts) == 3
    assert verdicts[0].passed   # f1: strong
    assert not verdicts[1].passed  # f2: weak
    assert verdicts[2].passed   # f3: borderline but passes


def test_summary_markdown():
    """Summary markdown should render without error."""
    gate = ValidationGate()
    factors = [
        {"name": "f1", "ic_mean": 0.050, "ic_ir": 0.80, "oos_retention": 0.85},
        {"name": "f2", "ic_mean": 0.010, "ic_ir": 0.15, "oos_retention": 0.30},
    ]
    verdicts = gate.batch_evaluate(factors)
    md = gate.summary_markdown(verdicts)
    assert "f1" in md
    assert "f2" in md
    assert "✅" in md
    assert "❌" in md


def test_gate_verdict_to_dict():
    """GateVerdict.to_dict should be JSON-serializable."""
    gate = ValidationGate()
    verdict = gate.evaluate("test", ic_mean=0.04, ic_ir=0.60, oos_retention=0.80)
    d = verdict.to_dict()
    json.dumps(d)  # Should not raise
    assert d["factor_name"] == "test"
    assert d["passed"] is True


if __name__ == "__main__":
    test_gate_all_pass()
    test_gate_all_fail()
    test_gate_borderline()
    test_gate_missing_data()
    test_gate_cost_resilience()
    test_gate_sector_neutrality()
    test_gate_segment_consistency()
    test_batch_evaluate()
    test_summary_markdown()
    test_gate_verdict_to_dict()
    print("✅ All 10 validation gate tests passed!")
