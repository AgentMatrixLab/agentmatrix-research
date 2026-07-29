"""
Unit tests for the jq_gm factor library.

Test categories:
  1. Spec format validation — every spec has required fields.
  2. Compute stub — no-GM mode returns correct column structure.
  3. CLI integration — list/export commands produce valid output.

These tests run in CI (no GM SDK), so they verify the pipeline
plumbing, not numerical correctness.
"""

from __future__ import annotations

import pytest

from research_core.factor_lab.libraries.jq_gm.specs import (
    JQ_GM_IMPLEMENTED_FACTORS,
    jq_gm_specs,
)
from research_core.factor_lab.libraries.jq_gm.factors import (
    compute_jq_gm_factors,
)

# ── Spec format tests ────────────────────────────────────────────

class TestSpecFormat:
    """Every FactorResearchSpec must pass structural validation.

    FactorResearchSpec has 18 fields (see contracts/factor_research.py).
    These tests validate that every one of the 30 shipped specs has
    complete and well-formed content, so the factor_lab validation
    pipeline won't encounter surprises downstream.
    """

    # ── Required value fields ──────────────────────────────────

    def test_all_specs_have_required_fields(self):
        """required_fields must be a non-empty list of strings."""
        for spec in jq_gm_specs():
            assert spec.required_fields, (
                f"{spec.factor_name}: required_fields is empty"
            )
            assert all(isinstance(f, str) and f.strip() for f in spec.required_fields), (
                f"{spec.factor_name}: required_fields must be non-empty strings"
            )

    def test_all_specs_have_formula(self):
        """formula must be a non-empty string."""
        for spec in jq_gm_specs():
            assert isinstance(spec.formula, str) and spec.formula.strip(), (
                f"{spec.factor_name}: formula is empty or not a string"
            )

    def test_all_specs_have_display_name(self):
        """display_name must be a non-empty string (Chinese name for humans)."""
        for spec in jq_gm_specs():
            assert isinstance(spec.display_name, str) and spec.display_name.strip(), (
                f"{spec.factor_name}: display_name is empty"
            )

    def test_all_specs_have_description(self):
        """description must be set (defaults to formula if not explicit)."""
        for spec in jq_gm_specs():
            assert isinstance(spec.description, str) and spec.description.strip(), (
                f"{spec.factor_name}: description is empty"
            )

    # ── Fixed-value fields (all jq_gm specs share these) ──────

    def test_library_and_version_are_correct(self):
        """Every spec must belong to jq_gm and use the current version."""
        for spec in jq_gm_specs():
            assert spec.library == "jq_gm", (
                f"{spec.factor_name}: library={spec.library}, expected jq_gm"
            )
            assert spec.version == "v2026.06", (
                f"{spec.factor_name}: version={spec.version}, expected v2026.06"
            )

    def test_frequency_is_day(self):
        """All jq_gm factors operate at daily frequency."""
        for spec in jq_gm_specs():
            assert spec.frequency == "day", (
                f"{spec.factor_name}: frequency={spec.frequency}, expected day"
            )

    def test_source_document_is_set(self):
        """Every spec must cite the JoinQuant taxonomy as its source."""
        for spec in jq_gm_specs():
            assert "JoinQuant" in spec.source_document or "jq_gm" in spec.library, (
                f"{spec.factor_name}: source_document missing JoinQuant reference"
            )

    def test_sample_scope_is_set(self):
        """sample_scope defines the stock universe for this factor."""
        for spec in jq_gm_specs():
            assert isinstance(spec.sample_scope, str) and len(spec.sample_scope) > 10, (
                f"{spec.factor_name}: sample_scope too short or missing"
            )

    # ── Validation targets ─────────────────────────────────────

    def test_all_specs_have_validation_targets(self):
        """Every spec must have exactly 4 validation targets."""
        for spec in jq_gm_specs():
            assert len(spec.validation_targets) == 4, (
                f"{spec.factor_name}: expected 4 validation targets, "
                f"got {len(spec.validation_targets)}"
            )

    def test_validation_targets_have_required_fields(self):
        """Each validation target needs metric, operator, value, description."""
        for spec in jq_gm_specs():
            for vt in spec.validation_targets:
                assert vt.metric and isinstance(vt.metric, str), (
                    f"{spec.factor_name}: validation target has empty metric"
                )
                assert vt.operator in (">=", "<=", ">", "<", "=="), (
                    f"{spec.factor_name}: invalid operator '{vt.operator}'"
                )
                assert isinstance(vt.value, (int, float)), (
                    f"{spec.factor_name}: validation value is not numeric"
                )

    # ── Tags ───────────────────────────────────────────────────

    def test_all_specs_have_category_tag(self):
        """Every spec must have at least one tag (the factor category)."""
        for spec in jq_gm_specs():
            assert len(spec.tags) >= 1, (
                f"{spec.factor_name}: tags is empty, expected at least category"
            )
            assert all(isinstance(t, str) and t.strip() for t in spec.tags), (
                f"{spec.factor_name}: tags contain empty or non-string values"
            )

    # ── Metadata ───────────────────────────────────────────────

    def test_all_specs_have_gm_metadata(self):
        """Every spec must carry gm_field, gm_fields, status, implementation_stage."""
        for spec in jq_gm_specs():
            assert spec.metadata.get("gm_field"), (
                f"{spec.factor_name}: missing gm_field in metadata"
            )
            assert spec.metadata.get("gm_fields"), (
                f"{spec.factor_name}: missing gm_fields in metadata"
            )
            assert spec.metadata.get("status") == "implemented", (
                f"{spec.factor_name}: metadata.status={spec.metadata.get('status')}"
            )
            assert spec.metadata.get("implementation_stage") == "code", (
                f"{spec.factor_name}: metadata.implementation_stage={spec.metadata.get('implementation_stage')}"
            )

    # ── List fields ─────────────────────────────────────────────

    def test_notes_and_preprocessing_are_lists(self):
        """notes and preprocessing must be lists of strings."""
        for spec in jq_gm_specs():
            assert isinstance(spec.notes, list), (
                f"{spec.factor_name}: notes is not a list"
            )
            assert all(isinstance(n, str) for n in spec.notes), (
                f"{spec.factor_name}: notes contain non-string values"
            )
            assert isinstance(spec.preprocessing, list), (
                f"{spec.factor_name}: preprocessing is not a list"
            )
            assert all(isinstance(p, str) for p in spec.preprocessing), (
                f"{spec.factor_name}: preprocessing contains non-string values"
            )
            assert isinstance(spec.neutralization, list), (
                f"{spec.factor_name}: neutralization is not a list"
            )

    # ── Uniqueness and count ───────────────────────────────────

    def test_factor_names_are_unique(self):
        """No duplicate factor names in the spec list."""
        names = [spec.factor_name for spec in jq_gm_specs()]
        assert len(names) == len(set(names)), (
            f"Duplicate factor names: {sorted(names)}"
        )

    def test_implemented_factors_match_specs(self):
        """JQ_GM_IMPLEMENTED_FACTORS must match the spec list exactly."""
        spec_names = sorted(spec.factor_name for spec in jq_gm_specs())
        impl_names = sorted(JQ_GM_IMPLEMENTED_FACTORS)
        assert spec_names == impl_names, (
            f"Mismatch: specs={spec_names}, implemented={impl_names}"
        )

    def test_spec_count_is_215(self):
        """All 215 non-Alpha factors are registered."""
        assert len(jq_gm_specs()) == 215, (
            f"Expected 30 factors, got {len(jq_gm_specs())}"
        )


# ── Compute stub tests ───────────────────────────────────────────

class TestComputeStub:
    """In the absence of GM SDK, compute should return NaN frames."""

    def test_stub_returns_correct_columns(self):
        """Stub mode returns date, code, and all factor columns."""
        import pandas as pd

        panel = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02"],
            "code": ["SHSE.600519", "SZSE.000001"],
            "close": [100.0, 50.0],
        })
        factor_names = ["pe_ttm", "roe_ttm", "market_cap"]

        result = compute_jq_gm_factors(panel, factor_names)

        assert list(result.columns) == ["date", "code", *factor_names]
        assert len(result) == 2
        # All factor values should be NaN in stub mode.
        for col in factor_names:
            assert result[col].isna().all()

    def test_stub_handles_empty_factor_list(self):
        """Empty factor list returns just date/code columns."""
        import pandas as pd

        panel = pd.DataFrame({
            "date": ["2024-01-01"],
            "code": ["SHSE.600519"],
        })
        result = compute_jq_gm_factors(panel, [])
        assert list(result.columns) == ["date", "code"]
        assert len(result) == 1
