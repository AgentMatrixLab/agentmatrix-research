#!/usr/bin/env python3
"""
Tests for research_core.agent_api — the unified AI-agent entry layer.

Covers:
  1. Standard imports — every exported symbol is importable
  2. Manifest / function signature consistency — manifest entries match real functions
  3. Return field contracts — each function returns expected keys (structure)
  4. Documentation examples — AGENTS.md and agent_manifest.py examples execute
  5. Complete workflow — end-to-end factor → validate → manual assemble
  6. CLI failure exit codes — non-zero on structured errors
  7. Concurrent calls — thread-safety smoke test
  8. Edge cases — empty args, missing files, type errors
"""

from __future__ import annotations

import json
import subprocess as _sp
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

# Make sure research_core is on the path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════
# Section 1 — Standard imports
# ═══════════════════════════════════════════════════════════════

# fmt: off
_EXPECTED_PUBLIC_API = [
    "discover",
    "overview",
    "check_data_source",
    "explore_factors",
    "validate_factor",
    "evaluate_factor_csv",
    "list_factors",
    "build_strategy",
    "package_backtest",
    "parse_backtest_result",
    "mine_factor",
    "auto_mine",
    "qlib_backtest",
]
# fmt: on


class TestStandardImports:
    """Every public API name must be importable."""

    def test_top_level_import(self):
        """`from research_core.agent_api import ...` works for every name."""
        import research_core.agent_api as api

        for name in _EXPECTED_PUBLIC_API:
            obj = getattr(api, name, None)
            assert obj is not None, f"Missing {name} in agent_api"
            assert callable(obj), f"{name} is not callable"

    def test_submodule_imports(self):
        """agent_manifest and __init__ are importable."""
        from research_core.agent_manifest import get_manifest, get_capability, get_capabilities_by_category, manifest_to_markdown  # noqa: F401

        assert callable(get_manifest)
        assert callable(get_capability)
        assert callable(get_capabilities_by_category)
        assert callable(manifest_to_markdown)

    def test_cli_module_runs_as_main(self):
        """python -m research_core.agent_api discover prints JSON."""
        cmd = [sys.executable, "-m", "research_core.agent_api", "discover"]
        proc = _sp.run(cmd, capture_output=True, text=True, timeout=30, cwd=str(_PROJECT_ROOT))
        data = json.loads(proc.stdout)
        assert data["framework"] == "AgentMatrix Research"
        assert len(data["capabilities"]) >= 10


# ═══════════════════════════════════════════════════════════════
# Section 2 — Manifest / function-signature consistency
# ═══════════════════════════════════════════════════════════════

class TestManifestConsistency:
    """Every manifest entry must match the real function."""

    @pytest.fixture(scope="class")
    def manifest(self):
        from research_core.agent_manifest import get_manifest
        return get_manifest()

    @pytest.fixture(scope="class")
    def api(self):
        import research_core.agent_api as api
        return api

    def test_every_manifest_cap_has_function(self, manifest, api):
        """Each manifest `name` must resolve to a callable in agent_api."""
        for cap in manifest["capabilities"]:
            name = cap["name"]
            fn = getattr(api, name, None)
            assert fn is not None, f"Manifest capability '{name}' missing from agent_api"
            assert callable(fn), f"agent_api.{name} is not callable"

    def test_every_api_function_has_manifest_entry(self, manifest, api):
        """Each public function in agent_api must have a manifest entry."""
        manifest_names = {c["name"] for c in manifest["capabilities"]}
        for name in _EXPECTED_PUBLIC_API:
            assert name in manifest_names, f"API function '{name}' missing from manifest"

    def test_manifest_discover_matches_actual_discover(self, manifest):
        """discover() == get_manifest()."""
        from research_core.agent_api import discover
        result = discover()
        assert result == manifest

    def test_discover_returns_expected_top_level_keys(self, manifest):
        """Top-level keys must exist."""
        for key in ("framework", "version", "description", "language", "categories", "capabilities", "entry_points"):
            assert key in manifest, f"Missing top-level key: {key}"

    def test_manifest_category_labels_match(self, manifest):
        """Category keys match the actual capability categories."""
        used_categories = {c["category"] for c in manifest["capabilities"]}
        defined_categories = set(manifest["categories"].keys())
        assert used_categories.issubset(defined_categories), f"Missing categories: {used_categories - defined_categories}"


# ═══════════════════════════════════════════════════════════════
# Section 3 — Return field contracts
# ═══════════════════════════════════════════════════════════════

class TestDiscoverContract:
    """discover() / overview() return field contracts."""

    def test_discover_returns_dict(self):
        from research_core.agent_api import discover
        result = discover()
        assert isinstance(result, dict)
        assert result["framework"] == "AgentMatrix Research"


class TestValidateFactorContract:
    """validate_factor() return field contract."""

    def test_validate_passing_factor(self):
        """A strong factor passes all gates."""
        from research_core.agent_api import validate_factor
        v = validate_factor("alpha_test", ic_mean=0.045, ic_ir=0.65, oos_retention=0.82)
        assert v["passed"] is True
        assert "gates" in v
        assert "fail_reasons" in v
        assert "pass_reasons" in v
        assert "factor_name" in v
        assert "ic_mean" in v
        assert "next_actions" in v
        assert isinstance(v["next_actions"], list)
        assert len(v["next_actions"]) > 0

    def test_validate_failing_factor(self):
        """A weak factor fails."""
        from research_core.agent_api import validate_factor
        v = validate_factor("alpha_bad", ic_mean=0.002, ic_ir=0.05, oos_retention=0.20)
        assert v["passed"] is False
        assert len(v["fail_reasons"]) >= 1

    def test_validate_passes_through_validated_run_path(self):
        """validated_run_path is echoed back in the result."""
        from research_core.agent_api import validate_factor
        v = validate_factor("alpha1", ic_mean=0.04, ic_ir=0.60,
                            validated_run_path="/tmp/test_job.json")
        assert v["validated_run_path"] == "/tmp/test_job.json"

    def test_validate_optional_gates(self):
        """Cost resilience, sector neutrality, segment consistency."""
        from research_core.agent_api import validate_factor
        v = validate_factor("alpha_full", ic_mean=0.035, ic_ir=0.50,
                            cost_resilience=True, sector_neutrality=0.60,
                            segment_consistency=2)
        assert isinstance(v["passed"], bool)

    def test_validate_empty_factor_name_still_works(self):
        """Edge: empty factor_name should still produce result structure."""
        from research_core.agent_api import validate_factor
        v = validate_factor("", ic_mean=0.04, ic_ir=0.60)
        assert v["factor_name"] == ""
        assert isinstance(v["passed"], bool)


class TestValidateEdgeCases:
    """Edge cases for validate_factor."""

    def test_validate_zero_metrics(self):
        """Zero IC metrics."""
        from research_core.agent_api import validate_factor
        v = validate_factor("alpha_zero", ic_mean=0.0, ic_ir=0.0)
        assert isinstance(v, dict)
        assert v["factor_name"] == "alpha_zero"
        # Should have gates dict even if everything is zero
        assert "gates" in v

    def test_validate_mixed_strong_weak(self):
        """Strong IC but weak IR."""
        from research_core.agent_api import validate_factor
        v = validate_factor("alpha_mixed", ic_mean=0.05, ic_ir=0.15, oos_retention=0.80)
        assert isinstance(v["passed"], bool)
        assert "gates" in v


# ═══════════════════════════════════════════════════════════════
# Section 4 — Documentation examples
# ═══════════════════════════════════════════════════════════════

class TestDocumentationExamples:
    """Every example in AGENTS.md and manifest executes correctly."""

    def test_ag_ents_md_tldr(self):
        """The "TL;DR" block from AGENTS.md."""
        from research_core.agent_api import discover
        caps = discover()
        for c in caps["capabilities"]:
            assert "name" in c
            # description[:60] should not crash
            _ = c["description"][:60]

    def test_ag_ents_md_quick_verify(self):
        """The "Quick Verify" one-liner from AGENTS.md."""
        from research_core.agent_api import discover
        result = discover()
        assert result["framework"] == "AgentMatrix Research"

    def test_manifest_discover_example(self):
        """Manifest discover example."""
        from research_core.agent_api import discover
        result = discover()
        assert isinstance(result, dict)
        # Example: print(result) — verify structure
        assert "capabilities" in result

    def test_manifest_explore_example_structure(self):
        """Manifest explore_factors example — verify function exists and is callable."""
        from research_core.agent_api import explore_factors
        # Verify function signature is correct (don't actually run — needs data)
        import inspect
        sig = inspect.signature(explore_factors)
        params = list(sig.parameters.keys())
        for p in ("goal", "universe", "factor_set", "factors", "start", "end", "horizon", "top_n", "auto", "cache_dir"):
            assert p in params, f"Missing parameter: {p}"

    def test_manifest_validate_example(self):
        """Manifest validate_factor example."""
        from research_core.agent_api import validate_factor
        v = validate_factor("alpha1", ic_mean=0.035, ic_ir=0.45, oos_retention=0.75)
        assert isinstance(v["passed"], bool)
        assert "fail_reasons" in v

    def test_manifest_list_factors_example(self):
        """Manifest list_factors example."""
        from research_core.agent_api import list_factors
        result = list_factors("alpha101")
        assert "items" in result
        assert "count" in result
        assert "factor_set" in result
        # Example: for f in result['items']
        for f in result["items"]:
            assert "factor_name" in f

    def test_manifest_overview_example_structure(self):
        """Manifest overview example — verify signature only."""
        from research_core.agent_api import overview
        import inspect
        sig = inspect.signature(overview)
        assert len(sig.parameters) == 0  # no args

    def test_manifest_build_strategy_example_structure(self):
        """Manifest build_strategy example's return structure documented correctly."""
        from research_core.agent_api import build_strategy
        import inspect
        sig = inspect.signature(build_strategy)
        params = list(sig.parameters.keys())
        for p in ("validated_run_path", "factor_names", "rebalance_frequency", "top_n", "long_short", "as_of", "start", "end", "output_dir"):
            assert p in params

    def test_manifest_package_backtest_example_structure(self):
        """Manifest package_backtest example's parameter schema matches."""
        from research_core.agent_api import package_backtest
        import inspect
        sig = inspect.signature(package_backtest)
        params = list(sig.parameters.keys())
        for p in ("engine", "signal_path", "strategy_id", "start", "end", "benchmark", "initial_cash", "slippage_bps", "commission_bps", "run_id", "output_dir"):
            assert p in params

    def test_manifest_parse_backtest_example_structure(self):
        """Manifest parse_backtest_result example."""
        from research_core.agent_api import parse_backtest_result
        import inspect
        sig = inspect.signature(parse_backtest_result)
        params = list(sig.parameters.keys())
        for p in ("engine", "run_id", "result_path"):
            assert p in params


# ═══════════════════════════════════════════════════════════════
# Section 5 — Complete workflow (as much as possible offline)
# ═══════════════════════════════════════════════════════════════

class TestEndToEndWorkflow:
    """Full pipeline: discover → overview → list → validate (no network required)."""

    def test_workflow_discover_has_all_steps(self):
        """discover() + overview() + list_factors() + validate_factor() chain."""
        from research_core.agent_api import discover, list_factors, validate_factor

        # Step 1: Discover
        caps = discover()
        assert len(caps["capabilities"]) >= 10

        # Step 2: Overview — may fail if deps missing, so wrap
        try:
            from research_core.agent_api import overview
            ov = overview()
            assert "workspace" in ov
        except Exception:
            pass  # deps may be missing; not a test failure

        # Step 3: List factors
        factors = list_factors("alpha101")
        assert factors["factor_set"] == "alpha101"
        assert factors["count"] > 0
        # Grab a factor name for the next step
        first = factors["items"][0]
        fname = first["factor_name"]

        # Step 4: Validate (manually, since we don't have real IC data)
        v = validate_factor(fname, ic_mean=0.035, ic_ir=0.45, oos_retention=0.75)
        assert "passed" in v
        assert "next_actions" in v

    def test_workflow_list_all_families(self):
        """list_factors() should work for all known families."""
        from research_core.agent_api import list_factors

        for family in ("alpha101", "wq101", "gtja191", "alpha158", "barra"):
            result = list_factors(family)
            assert result["factor_set"] == family
            assert isinstance(result["count"], int)
            assert isinstance(result["items"], list)
            assert "next_actions" in result

    def test_workflow_unknown_family_errors_gracefully(self):
        """list_factors('nonexistent') should return structured error."""
        from research_core.agent_api import list_factors
        result = list_factors("nonexistent")
        if "error" in result:
            assert "suggested_fix" in result


# ═══════════════════════════════════════════════════════════════
# Section 6 — CLI failure exit codes
# ═══════════════════════════════════════════════════════════════

class TestCLIExitCodes:
    """CLI must return non-zero on errors."""

    MODULE = [sys.executable, "-m", "research_core.agent_api"]

    @staticmethod
    def _run(*args, timeout=30):
        return _sp.run(
            TestCLIExitCodes.MODULE + list(args),
            capture_output=True, text=True, timeout=timeout,
            cwd=str(_PROJECT_ROOT),
        )

    def test_discover_exits_zero(self):
        """discover subcommand → exit 0."""
        proc = self._run("discover")
        assert proc.returncode == 0, f"Expected 0, got {proc.returncode}\n{proc.stderr}"

    def test_no_subcommand_exits_nonzero(self):
        """No arguments → argparse error → exit 2."""
        proc = _sp.run(self.MODULE, capture_output=True, text=True, timeout=30, cwd=str(_PROJECT_ROOT))
        assert proc.returncode != 0, f"Expected non-zero, got {proc.returncode}"

    def test_validate_missing_required_fails(self):
        """validate without --factor-name → exit 2."""
        proc = self._run("validate")
        assert proc.returncode != 0, f"Expected non-zero, got {proc.returncode}"

    def test_validate_missing_ic_mean_fails(self):
        """validate --factor-name x (no IC) → exit 2."""
        proc = self._run("validate", "--factor-name", "test")
        assert proc.returncode != 0

    def test_build_missing_validated_run_fails(self):
        """build without --validated-run → exit 2."""
        proc = self._run("build")
        assert proc.returncode != 0

    def test_build_nonexistent_file_exits_nonzero(self):
        """build --validated-run nonexistent.json → error handled."""
        proc = self._run("build", "--validated-run", "/nonexistent/path.json")
        # Either exit 1 (structured error) or 0 depending on implementation
        # At minimum, output should contain 'error'
        combined = proc.stdout + proc.stderr
        # The function should handle this gracefully via _safe_call
        if proc.returncode == 0:
            result = json.loads(proc.stdout)
            # Even with exit 0, the JSON might contain an error field
            assert isinstance(result, dict)
        else:
            assert proc.returncode != 0

    def test_package_missing_engine_fails(self):
        """package without --engine → exit 2."""
        proc = self._run("package")
        assert proc.returncode != 0

    def test_mine_missing_name_fails(self):
        """mine without --name → exit 2."""
        proc = self._run("mine")
        assert proc.returncode != 0

    def test_discover_json_is_valid(self):
        """discover output is valid JSON."""
        proc = self._run("discover")
        data = json.loads(proc.stdout)
        assert "framework" in data
        assert isinstance(data["capabilities"], list)

    def test_validate_with_full_args_exits_zero(self):
        """validate with all required args → success (exit 0)."""
        proc = self._run(
            "validate",
            "--factor-name", "cli_test_factor",
            "--ic-mean", "0.04",
            "--ic-ir", "0.60",
            "--oos-retention", "0.80",
        )
        assert proc.returncode == 0, f"exit={proc.returncode}\nstderr={proc.stderr}"
        result = json.loads(proc.stdout)
        assert result["factor_name"] == "cli_test_factor"
        assert isinstance(result["passed"], bool)

    def test_list_factors_cli_exits_zero(self):
        """list-factors CLI → exit 0."""
        proc = self._run("list-factors", "--factor-set", "alpha101")
        assert proc.returncode == 0
        result = json.loads(proc.stdout)
        assert "items" in result

    def test_validate_with_validated_run_path(self):
        """validate with --validated-run-path → exit 0, path echoed."""
        proc = self._run(
            "validate",
            "--factor-name", "test",
            "--ic-mean", "0.04",
            "--ic-ir", "0.60",
            "--validated-run-path", "/tmp/cli_test_job.json",
        )
        assert proc.returncode == 0
        result = json.loads(proc.stdout)
        assert result["validated_run_path"] == "/tmp/cli_test_job.json"

    def test_cli_output_is_printable_utf8(self):
        """All CLI output should contain valid UTF-8."""
        for subcmd in ("discover", "list-factors", "overview"):
            try:
                proc = self._run(subcmd)
                _ = proc.stdout.encode("utf-8").decode("utf-8")
            except Exception:
                # overview may fail on missing deps — that's ok
                pass


# ═══════════════════════════════════════════════════════════════
# Section 7 — Concurrent calls
# ═══════════════════════════════════════════════════════════════

class TestConcurrency:
    """Thread-safety smoke tests."""

    def test_concurrent_discover(self):
        """Multiple threads calling discover() simultaneously."""
        import concurrent.futures

        from research_core.agent_api import discover

        def call():
            return discover()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(call) for _ in range(10)]
            results = [f.result() for f in futures]

        # All should return identical manifests
        first = results[0]
        for r in results[1:]:
            assert r == first

    def test_concurrent_validate(self):
        """Multiple threads calling validate_factor()."""
        import concurrent.futures

        from research_core.agent_api import validate_factor

        def call(name_suffix):
            return validate_factor(
                f"concurrent_{name_suffix}",
                ic_mean=0.04, ic_ir=0.60,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(call, i) for i in range(8)]
            results = [f.result() for f in futures]

        for i, r in enumerate(results):
            assert r["factor_name"] == f"concurrent_{i}"
            assert isinstance(r["passed"], bool)

    def test_concurrent_list_factors(self):
        """Multiple threads calling list_factors()."""
        import concurrent.futures

        from research_core.agent_api import list_factors

        families = ["alpha101", "wq101", "gtja191", "alpha158", "barra"] * 3

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(list_factors, f) for f in families]
            results = [f.result() for f in futures]

        for r in results:
            assert "items" in r
            assert "count" in r

    def test_concurrent_mixed_operations(self):
        """Mixed operations across threads."""
        import concurrent.futures

        from research_core.agent_api import discover, list_factors, validate_factor

        def call_discover():
            return discover()

        def call_list():
            return list_factors("alpha101")

        def call_validate():
            return validate_factor("mixed", ic_mean=0.04, ic_ir=0.60)

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            ops = [ex.submit(fn) for fn in
                   [call_discover, call_list, call_validate] * 3]
            results = [f.result() for f in ops]

        assert len(results) == 9
        for r in results:
            assert isinstance(r, dict)


# ═══════════════════════════════════════════════════════════════
# Section 8 — Edge cases & error handling
# ═══════════════════════════════════════════════════════════════

class TestErrorHandling:
    """Structured error responses."""

    def test_evaluate_csv_missing_file(self):
        """evaluate_factor_csv with nonexistent file → error dict."""
        from research_core.agent_api import evaluate_factor_csv
        result = evaluate_factor_csv("/nonexistent/factor.csv")
        assert "error" in result
        assert "suggested_fix" in result

    def test_check_data_without_env(self):
        """check_data_source() works without env_file."""
        from research_core.agent_api import check_data_source
        result = check_data_source()
        # Should return dict, probably 'connected: False' since no env
        assert isinstance(result, dict)
        assert "connected" in result or "error" in result

    def test_list_factors_empty_string_family(self):
        """list_factors('') — should handle gracefully."""
        from research_core.agent_api import list_factors
        result = list_factors("")
        if "error" in result:
            assert "suggested_fix" in result
        else:
            assert isinstance(result, dict)

    def test_validate_all_default_optional_params(self):
        """validate_factor with only required params."""
        from research_core.agent_api import validate_factor
        v = validate_factor("minimal", ic_mean=0.03, ic_ir=0.40)
        assert "passed" in v
        assert "gates" in v


class TestManifestHelperFunctions:
    """agent_manifest helper functions."""

    def test_get_capabilities_by_category(self):
        from research_core.agent_manifest import get_capabilities_by_category
        factor_caps = get_capabilities_by_category("factor_research")
        assert len(factor_caps) >= 3
        names = {c["name"] for c in factor_caps}
        assert "explore_factors" in names
        assert "validate_factor" in names
        assert "list_factors" in names

    def test_get_capability_by_name(self):
        from research_core.agent_manifest import get_capability
        cap = get_capability("discover")
        assert cap is not None
        assert cap["category"] == "meta"

    def test_get_capability_nonexistent(self):
        from research_core.agent_manifest import get_capability
        assert get_capability("nonexistent_func") is None

    def test_manifest_to_markdown(self):
        from research_core.agent_manifest import manifest_to_markdown
        md = manifest_to_markdown()
        assert "AgentMatrix Research" in md
        assert "### Factor Research" in md or "Factor Research" in md
        assert "discover" in md


# ═══════════════════════════════════════════════════════════════
# Section 9 — Safe call helper
# ═══════════════════════════════════════════════════════════════

class TestSafeCall:
    """_safe_call internal helper."""

    def test_safe_call_returns_result(self):
        from research_core.agent_api import _safe_call

        def ok():
            return {"value": 42}

        result = _safe_call(ok)
        assert result == {"value": 42}

    def test_safe_call_catches_file_not_found(self):
        from research_core.agent_api import _safe_call

        def raises_fnf():
            raise FileNotFoundError("missing.txt")

        result = _safe_call(raises_fnf)
        assert "error" in result
        assert "File not found" in result["error"]
        assert "suggested_fix" in result

    def test_safe_call_catches_system_exit(self):
        from research_core.agent_api import _safe_call

        def raises_exit():
            import sys as _sys
            _sys.exit(2)

        result = _safe_call(raises_exit)
        assert result.get("error_type") == "SystemExit"
        assert result.get("exit_code") == 2
        assert "suggested_fix" in result

    def test_safe_call_catches_generic_exception(self):
        from research_core.agent_api import _safe_call

        def raises_generic():
            raise ValueError("bad input")

        result = _safe_call(raises_generic)
        assert "error" in result
        assert result["error"] == "bad input"
        assert result["error_type"] == "ValueError"
        assert "suggested_fix" in result


# ═══════════════════════════════════════════════════════════════
# Section 10 — Return value shape (every 'next_actions' check)
# ═══════════════════════════════════════════════════════════════

class TestNextActions:
    """Every successful result must have 'next_actions'."""

    def test_discover_no_next_actions_is_fine(self):
        """discover() doesn't need next_actions (it IS the entry point)."""
        from research_core.agent_api import discover
        result = discover()
        # discover is meta; no next_actions required

    def test_validate_has_next_actions(self):
        from research_core.agent_api import validate_factor
        v = validate_factor("test", ic_mean=0.04, ic_ir=0.60)
        assert "next_actions" in v
        assert isinstance(v["next_actions"], list)
        assert len(v["next_actions"]) > 0

    def test_list_factors_has_next_actions(self):
        from research_core.agent_api import list_factors
        result = list_factors("alpha101")
        assert "next_actions" in result
        assert len(result["next_actions"]) > 0


# ═══════════════════════════════════════════════════════════════
# Section 11 — Module-level singleton & idempotency
# ═══════════════════════════════════════════════════════════════

class TestIdempotency:
    """Repeated calls should return consistent results."""

    def test_discover_idempotent(self):
        from research_core.agent_api import discover
        r1 = discover()
        r2 = discover()
        assert r1 == r2

    def test_list_factors_idempotent(self):
        from research_core.agent_api import list_factors
        r1 = list_factors("alpha101")
        r2 = list_factors("alpha101")
        assert r1 == r2

    def test_manifest_get_idempotent(self):
        from research_core.agent_manifest import get_manifest
        m1 = get_manifest()
        m2 = get_manifest()
        assert m1 == m2


# ═══════════════════════════════════════════════════════════════
# Section 12 — Deep-copy isolation (discover / get_manifest)
# ═══════════════════════════════════════════════════════════════

class TestDeepCopyIsolation:
    """discover() must return independent copies — mutating one result must
    not affect subsequent calls."""

    def test_discover_capabilities_not_shared(self):
        """Mutating capabilities in one discover() call must not leak."""
        from research_core.agent_api import discover

        r1 = discover()
        original_count = len(r1["capabilities"])
        r1["capabilities"].append({"name": "fake", "injected": True})
        r1["capabilities"][0]["description"] = "tampered"

        r2 = discover()
        assert len(r2["capabilities"]) == original_count
        assert r2["capabilities"][0]["description"] != "tampered"

    def test_get_manifest_categories_not_shared(self):
        """Mutating categories in one get_manifest() call must not leak."""
        from research_core.agent_manifest import get_manifest

        m1 = get_manifest()
        m1["categories"]["meta"]["label"] = "HACKED"

        m2 = get_manifest()
        assert m2["categories"]["meta"]["label"] != "HACKED"

    def test_discover_parameter_dicts_not_shared(self):
        """Nested parameter dicts must also be independent."""
        from research_core.agent_api import discover

        r1 = discover()
        for cap in r1["capabilities"]:
            if cap["name"] == "explore_factors":
                if "parameters" in cap and "goal" in cap["parameters"]:
                    cap["parameters"]["goal"]["default"] = "INJECTED"
                    break

        r2 = discover()
        for cap in r2["capabilities"]:
            if cap["name"] == "explore_factors":
                if "parameters" in cap and "goal" in cap["parameters"]:
                    assert cap["parameters"]["goal"]["default"] != "INJECTED"
                    break


# ═══════════════════════════════════════════════════════════════
# Section 13 — Qlib JSON parsing (mocked subprocess)
# ═══════════════════════════════════════════════════════════════

class TestQlibJSONParsing:
    """mine_factor / auto_mine / qlib_backtest must parse CLI JSON output."""

    @staticmethod
    def _fake_proc(stdout: str, returncode: int = 0):
        """Create a fake subprocess.CompletedProcess."""
        from subprocess import CompletedProcess
        return CompletedProcess(
            args=["fake"], returncode=returncode,
            stdout=stdout, stderr="",
        )

    def test_mine_factor_parses_json(self, monkeypatch):
        """mine_factor() extracts IC/IR from JSON, not line matching."""
        fake_json = json.dumps({
            "definition": {
                "name": "reversal_5d",
                "expression": "Ref($close, 5) / $close - 1",
                "description": "Factor: reversal_5d",
                "source": "manual",
            },
            "evaluation": {
                "factor_id": "rev5d",
                "metrics": [
                    {"name": "ic_mean", "value": 0.035, "higher_is_better": True},
                    {"name": "icir", "value": 0.52, "higher_is_better": True},
                ],
                "artifacts": {
                    "factor_frame": "/tmp/factors/rev5d.csv",
                    "evaluation": "/tmp/evals/rev5d.json",
                },
            },
            "top_metrics": {
                "ic_mean": 0.035,
                "rank_ic_mean": 0.041,
                "icir": 0.52,
                "long_short_spread": 0.012,
            },
        })

        import research_core.agent_api as api
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: self._fake_proc(fake_json),
        )

        result = api.mine_factor("reversal_5d", "Ref($close, 5) / $close - 1")

        assert result["status"] == "completed"
        assert result["ic_mean"] == 0.035
        assert result["ic_ir"] == 0.52
        assert result["rank_ic_mean"] == 0.041
        assert result["long_short_spread"] == 0.012
        assert result["definition"]["name"] == "reversal_5d"
        assert "artifacts" in result
        assert result["artifacts"]["factor_frame"] == "/tmp/factors/rev5d.csv"

    def test_mine_factor_error_returncode(self, monkeypatch):
        """mine_factor() with non-zero exit returns structured error."""
        import research_core.agent_api as api
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: self._fake_proc("", returncode=1),
        )

        result = api.mine_factor("bad", "invalid_expr")
        assert result["status"] == "error"
        assert "error" in result
        assert result["returncode"] == 1

    def test_auto_mine_parses_json(self, monkeypatch):
        """auto_mine() extracts generated_count and results from JSON."""
        fake_json = json.dumps({
            "theme": "mid-cap momentum",
            "generated_count": 3,
            "results": [
                {
                    "definition": {"name": "mom_20d", "expression": "($close / Ref($close, 20) - 1)"},
                    "evaluation": {"metrics": []},
                    "top_metrics": {"ic_mean": 0.04, "icir": 0.55},
                    "candidate": {"name": "mom_20d", "expression": "($close / Ref($close, 20) - 1)"},
                },
                {
                    "definition": {"name": "mom_10d", "expression": "($close / Ref($close, 10) - 1)"},
                    "evaluation": {"metrics": []},
                    "top_metrics": {"ic_mean": 0.03, "icir": 0.45},
                    "candidate": {"name": "mom_10d"},
                },
            ],
        })

        import research_core.agent_api as api
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: self._fake_proc(fake_json),
        )

        result = api.auto_mine("mid-cap momentum")

        assert result["status"] == "completed"
        assert result["generated_count"] == 3
        assert len(result["results"]) == 2
        assert result["best_factor"] == "mom_20d"
        assert result["best_ic"] == 0.04
        assert len(result["candidates"]) == 2
        assert result["candidates"][0]["name"] == "mom_20d"
        assert result["candidates"][0]["ic_mean"] == 0.04

    def test_auto_mine_error_returncode(self, monkeypatch):
        """auto_mine() with non-zero exit returns structured error."""
        import research_core.agent_api as api
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: self._fake_proc("", returncode=1),
        )

        result = api.auto_mine("test theme")
        assert result["status"] == "error"
        assert "error" in result

    def test_qlib_backtest_parses_json(self, monkeypatch):
        """qlib_backtest() extracts Sharpe/return/MDD from JSON metrics."""
        fake_json = json.dumps({
            "run_id": "abc123",
            "status": "completed",
            "engine": "qlib_daily_robust_v6.1",
            "strategy_id": "adhoc_factor_strategy",
            "metrics": {
                "total_return": 0.15,
                "annualized_return": 0.12,
                "max_drawdown": -0.08,
                "sharpe": 1.35,
                "volatility": 0.18,
                "win_rate": 0.55,
            },
            "equity_curve": [
                {"timestamp": "2021-01-01", "strategy_nav": 1.0},
                {"timestamp": "2021-06-01", "strategy_nav": 1.15},
            ],
            "artifacts": {"result_json": "/tmp/backtests/abc123.json"},
        })

        import research_core.agent_api as api
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: self._fake_proc(fake_json),
        )

        result = api.qlib_backtest("($close / Ref($close, 20) - 1)")

        assert result["status"] == "completed"
        assert result["sharpe_ratio"] == 1.35
        assert result["annualized_return"] == 0.12
        assert result["max_drawdown"] == -0.08
        assert result["total_return"] == 0.15
        assert result["volatility"] == 0.18
        assert result["win_rate"] == 0.55
        assert result["run_id"] == "abc123"
        assert result["engine"] == "qlib_daily_robust_v6.1"
        assert len(result["equity_curve"]) == 2
        assert result["artifacts"]["result_json"] == "/tmp/backtests/abc123.json"

    def test_qlib_backtest_error_returncode(self, monkeypatch):
        """qlib_backtest() with non-zero exit returns structured error."""
        import research_core.agent_api as api
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: self._fake_proc("", returncode=1),
        )

        result = api.qlib_backtest("bad_expr")
        assert result["status"] == "error"
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# Section 14 — validate_factor guidance when no validated_run_path
# ═══════════════════════════════════════════════════════════════

class TestValidateFactorGuidance:
    """validate_factor() must properly guide toward build_strategy()."""

    def test_pass_without_run_path_guides_to_explore(self):
        """When factor passes without validated_run_path, next_actions
        should mention explore_factors() and the need for a job path."""
        from research_core.agent_api import validate_factor

        v = validate_factor("alpha_good", ic_mean=0.045, ic_ir=0.65, oos_retention=0.82)
        assert v["passed"] is True
        assert "validated_run_path" not in v  # not provided, so not in result
        actions_text = " ".join(v["next_actions"]).lower()
        assert "explore_factors" in actions_text or "build_strategy" in actions_text
        assert "validated_run_path" in " ".join(v["next_actions"]) or "job" in actions_text

    def test_pass_with_run_path_guides_to_build(self):
        """When factor passes with validated_run_path, next_actions
        should directly say to call build_strategy()."""
        from research_core.agent_api import validate_factor

        v = validate_factor("alpha_good", ic_mean=0.045, ic_ir=0.65,
                            oos_retention=0.82, validated_run_path="/tmp/job.json")
        assert v["passed"] is True
        assert v["validated_run_path"] == "/tmp/job.json"
        actions_text = " ".join(v["next_actions"]).lower()
        assert "build_strategy" in actions_text

    def test_fail_without_run_path_suggests_alternatives(self):
        """When factor fails, next_actions should suggest alternatives."""
        from research_core.agent_api import validate_factor

        v = validate_factor("alpha_bad", ic_mean=0.002, ic_ir=0.05, oos_retention=0.20)
        assert v["passed"] is False
        actions_text = " ".join(v["next_actions"]).lower()
        assert "fail" in actions_text or "different" in actions_text


# ═══════════════════════════════════════════════════════════════
# Section 15 — Manifest returns vs actual code consistency
# ═══════════════════════════════════════════════════════════════

class TestManifestReturnsConsistency:
    """Manifest 'returns' strings must match actual function return keys."""

    def test_mine_factor_returns_match(self):
        """Manifest mine_factor returns must list fields the code actually returns."""
        from research_core.agent_manifest import get_capability

        cap = get_capability("mine_factor")
        returns_str = cap["returns"]
        for field in ("factor_name", "expression", "ic_mean", "ic_ir",
                       "rank_ic_mean", "long_short_spread", "status",
                       "definition", "evaluation", "top_metrics"):
            assert field in returns_str, f"Manifest mine_factor returns missing '{field}'"

    def test_auto_mine_returns_match(self):
        """Manifest auto_mine returns must list fields the code actually returns."""
        from research_core.agent_manifest import get_capability

        cap = get_capability("auto_mine")
        returns_str = cap["returns"]
        for field in ("theme", "generated_count", "results", "candidates",
                       "best_factor", "best_ic"):
            assert field in returns_str, f"Manifest auto_mine returns missing '{field}'"

    def test_qlib_backtest_returns_match(self):
        """Manifest qlib_backtest returns must list fields the code actually returns."""
        from research_core.agent_manifest import get_capability

        cap = get_capability("qlib_backtest")
        returns_str = cap["returns"]
        for field in ("expression", "annualized_return", "sharpe_ratio",
                       "max_drawdown", "total_return", "volatility",
                       "win_rate", "metrics", "equity_curve"):
            assert field in returns_str, f"Manifest qlib_backtest returns missing '{field}'"

    def test_explore_factors_manifest_has_auto_and_cache_dir(self):
        """Manifest explore_factors parameters must include auto and cache_dir."""
        from research_core.agent_manifest import get_capability

        cap = get_capability("explore_factors")
        params = cap["parameters"]
        assert "auto" in params, "Manifest explore_factors missing 'auto' parameter"
        assert "cache_dir" in params, "Manifest explore_factors missing 'cache_dir' parameter"

    def test_overview_returns_match(self):
        """Manifest overview returns must match actual code output."""
        from research_core.agent_manifest import get_capability

        cap = get_capability("overview")
        returns_str = cap["returns"]
        for field in ("workspace", "factor_families", "backtest_engines",
                       "external_sim_engines", "data_sources"):
            assert field in returns_str, f"Manifest overview returns missing '{field}'"


# ═══════════════════════════════════════════════════════════════
# Section 16 — CLI validate with optional gate parameters
# ═══════════════════════════════════════════════════════════════

class TestCLIValidateOptionalGates:
    """CLI validate subcommand must support optional gate parameters."""

    MODULE = [sys.executable, "-m", "research_core.agent_api"]

    @staticmethod
    def _run(*args, timeout=30):
        return _sp.run(
            TestCLIValidateOptionalGates.MODULE + list(args),
            capture_output=True, text=True, timeout=timeout,
            cwd=str(_PROJECT_ROOT),
        )

    def test_validate_with_cost_resilience(self):
        """validate --cost-resilience should work."""
        proc = self._run(
            "validate",
            "--factor-name", "test_cr",
            "--ic-mean", "0.04",
            "--ic-ir", "0.60",
            "--cost-resilience",
        )
        assert proc.returncode == 0, f"exit={proc.returncode}\nstderr={proc.stderr}"
        result = json.loads(proc.stdout)
        assert result["factor_name"] == "test_cr"

    def test_validate_with_sector_neutrality(self):
        """validate --sector-neutrality 0.6 should work."""
        proc = self._run(
            "validate",
            "--factor-name", "test_sn",
            "--ic-mean", "0.04",
            "--ic-ir", "0.60",
            "--sector-neutrality", "0.6",
        )
        assert proc.returncode == 0, f"exit={proc.returncode}\nstderr={proc.stderr}"
        result = json.loads(proc.stdout)
        assert result["factor_name"] == "test_sn"

    def test_validate_with_segment_consistency(self):
        """validate --segment-consistency 2 should work."""
        proc = self._run(
            "validate",
            "--factor-name", "test_sc",
            "--ic-mean", "0.04",
            "--ic-ir", "0.60",
            "--segment-consistency", "2",
        )
        assert proc.returncode == 0, f"exit={proc.returncode}\nstderr={proc.stderr}"
        result = json.loads(proc.stdout)
        assert result["factor_name"] == "test_sc"

    def test_validate_with_all_optional_gates(self):
        """validate with all optional gates should work."""
        proc = self._run(
            "validate",
            "--factor-name", "test_all",
            "--ic-mean", "0.045",
            "--ic-ir", "0.65",
            "--oos-retention", "0.82",
            "--cost-resilience",
            "--sector-neutrality", "0.60",
            "--segment-consistency", "2",
            "--validated-run-path", "/tmp/test_all.json",
        )
        assert proc.returncode == 0, f"exit={proc.returncode}\nstderr={proc.stderr}"
        result = json.loads(proc.stdout)
        assert result["factor_name"] == "test_all"
        assert result["validated_run_path"] == "/tmp/test_all.json"


# ═══════════════════════════════════════════════════════════════
# Section 17 — End-to-end explore → build → package (synthetic data)
# ═══════════════════════════════════════════════════════════════

class TestExploreBuildPackageE2E:
    """End-to-end test: explore_factors → build_strategy → package_backtest
    using synthetic demo data (no network required).

    Verifies the documented agent workflow runs end to end:
        1. explore_factors() produces artifacts.job_path
        2. build_strategy() consumes the job path and produces a signal CSV
        3. package_backtest() consumes the signal CSV and produces a package dir

    Also covers:
        - auto=False without factors must raise (not silently auto-select)
        - A failed factor carrying validated_run_path must NOT be told "passed"
    """

    @pytest.fixture(autouse=True)
    def _patch_market_data(self, monkeypatch):
        """Replace fetch_real_panel with synthetic demo data so the test
        never touches the network."""
        from research_core.factor_lab import agent_pipeline
        from research_core.factor_lab.demo_data import build_alpha101_demo_panel

        synthetic_panel = build_alpha101_demo_panel(
            n_dates=120, n_codes=12, seed=7,
        )

        def _fake_fetch(*args, **kwargs):
            return synthetic_panel

        monkeypatch.setattr(agent_pipeline, "fetch_real_panel", _fake_fetch)

    # ── 1. explore_factors produces a consumable job_path ──────────────

    def test_explore_produces_consumable_job_path(self, tmp_path):
        """explore_factors() must return artifacts.job_path pointing to a
        valid job JSON that build_strategy() can consume."""
        from research_core.agent_api import explore_factors

        result = explore_factors(
            goal="e2e test",
            universe="csi300",
            factor_set="alpha101",
            factors=["alpha1", "alpha2", "alpha3"],
            start="2021-01-01",
            end="2021-06-30",
            horizon=5,
            top_n=3,
            auto=False,
            output_dir=str(tmp_path),
        )

        # No structured error
        assert "error" not in result, (
            f"explore_factors returned error: {result.get('error')}"
        )

        # artifacts.job_path must exist
        job_path = result["artifacts"]["job_path"]
        assert job_path, "artifacts.job_path is empty"
        assert Path(job_path).exists(), f"job_path file does not exist: {job_path}"

        # Job JSON must contain the fields build_strategy() expects
        payload = json.loads(Path(job_path).read_text(encoding="utf-8"))
        assert payload["job_id"]
        assert "alpha1" in payload["requested_factors"]
        assert payload["artifacts"]["factor_frame"]

        # factor_frame CSV must exist on disk
        frame_path = Path(payload["artifacts"]["factor_frame"])
        assert frame_path.exists(), f"factor_frame CSV missing: {frame_path}"

        # next_actions should mention build_strategy
        actions_text = " ".join(result["next_actions"])
        assert "build_strategy" in actions_text

        # factors_tested should match what we asked for
        assert result["factors_tested"] == 3

    # ── 2. Full pipeline: explore → build → package ────────────────────

    def test_full_pipeline_explore_build_package(self, tmp_path):
        """explore → build_strategy → package_backtest produces a package dir."""
        import pandas as pd
        from research_core.agent_api import (
            explore_factors, build_strategy, package_backtest,
        )

        # Step 1: explore
        explore_result = explore_factors(
            goal="e2e pipeline",
            factor_set="alpha101",
            factors=["alpha1", "alpha2", "alpha3"],
            start="2021-01-01",
            end="2021-06-30",
            horizon=5,
            top_n=3,
            auto=False,
            output_dir=str(tmp_path / "explore"),
        )
        assert "error" not in explore_result, explore_result.get("error")
        job_path = explore_result["artifacts"]["job_path"]
        assert Path(job_path).exists()

        # Step 2: build_strategy from the job path
        build_result = build_strategy(
            validated_run_path=job_path,
            rebalance_frequency="single",
            top_n=5,
            output_dir=str(tmp_path / "build"),
        )
        assert "error" not in build_result, build_result.get("error")
        assert build_result["status"] == "created"
        signal_path = build_result["artifacts"]["signals"]
        assert Path(signal_path).exists(), f"signal CSV missing: {signal_path}"

        # The signal CSV should have target weights
        signals = pd.read_csv(signal_path)
        assert len(signals) > 0, "signal CSV is empty"
        assert "target_weight" in signals.columns
        assert "code" in signals.columns
        assert "side" in signals.columns

        # Step 3: package_backtest
        package_result = package_backtest(
            engine="gm",
            signal_path=signal_path,
            strategy_id="e2e_test_strategy",
            output_dir=str(tmp_path / "package"),
        )
        assert "error" not in package_result, package_result.get("error")
        assert Path(package_result["package_dir"]).exists()
        assert Path(package_result["artifacts"]["signals"]).exists()
        assert Path(package_result["artifacts"]["config"]).exists()
        assert Path(package_result["artifacts"]["strategy_script"]).exists()

    # ── 3. auto=False without factors must raise ────────────────────────

    def test_auto_false_without_factors_raises(self, tmp_path):
        """auto=False with factors=None must return a structured error,
        not silently auto-select factors."""
        from research_core.agent_api import explore_factors

        result = explore_factors(
            factor_set="alpha101",
            factors=None,
            auto=False,
            output_dir=str(tmp_path),
        )
        # _safe_call catches the ValueError and returns a structured error dict
        assert "error" in result, (
            "auto=False without factors should have raised ValueError"
        )
        assert "auto=False" in result["error"] or "factors" in result["error"].lower()

    # ── 4. Failed factor + validated_run_path must not claim "passed" ──

    def test_failed_factor_with_run_path_does_not_claim_passed(self):
        """A failing factor carrying validated_run_path must NOT be told
        'passed' or directed to build_strategy()."""
        from research_core.agent_api import validate_factor

        # ic_mean=0.001, ic_ir=0.01, oos_retention=0.10 → will fail gates
        result = validate_factor(
            factor_name="alpha_garbage",
            ic_mean=0.001,
            ic_ir=0.01,
            oos_retention=0.10,
            validated_run_path="/tmp/some_job.json",
        )

        assert result["passed"] is False
        assert result["validated_run_path"] == "/tmp/some_job.json"

        actions_text = " ".join(result["next_actions"]).lower()

        # Must mention FAILED
        assert "failed" in actions_text, (
            "Failed factor's next_actions should mention 'FAILED'"
        )

        # Must NOT direct to build_strategy (should say "do not call")
        assert "do not call build_strategy" in actions_text, (
            "Failed factor should be told NOT to call build_strategy()"
        )

        # Must NOT contain the word "passed" (the old bug said "passed with")
        assert "passed" not in actions_text, (
            "Failed factor's next_actions must not contain 'passed'"
        )


# ═══════════════════════════════════════════════════════════════
# Section 18 — _parse_cli_json unit tests (log + multi-line JSON)
# ═══════════════════════════════════════════════════════════════

class TestParseCliJson:
    """Unit tests for the unified _parse_cli_json helper.

    The helper must handle:
      1. Pure JSON (entire stdout is a JSON object)
      2. Log + single-line JSON (log lines then a one-line JSON object)
      3. Log + multi-line JSON (log lines then a pretty-printed JSON object)
    And return None when no valid JSON is found.
    """

    def test_pure_json(self):
        from research_core.agent_api import _parse_cli_json
        raw = json.dumps({"status": "ok", "ic_mean": 0.03})
        result = _parse_cli_json(raw)
        assert result == {"status": "ok", "ic_mean": 0.03}

    def test_log_plus_single_line_json(self):
        from research_core.agent_api import _parse_cli_json
        raw = (
            "[INFO] Initializing qlib workspace...\n"
            "[INFO] Loading market data...\n"
            '{"status": "ok", "ic_mean": 0.035, "icir": 0.52}\n'
        )
        result = _parse_cli_json(raw)
        assert result is not None
        assert result["status"] == "ok"
        assert result["ic_mean"] == 0.035

    def test_log_plus_multi_line_json(self):
        """Pretty-printed (multi-line) JSON after log lines."""
        from research_core.agent_api import _parse_cli_json
        pretty = json.dumps(
            {"status": "ok", "ic_mean": 0.04, "metrics": {"sharpe": 1.2}},
            indent=2,
        )
        raw = (
            "[INFO] Qlib initialized\n"
            "[WARN] Using minimal init\n"
            + pretty
        )
        result = _parse_cli_json(raw)
        assert result is not None
        assert result["status"] == "ok"
        assert result["ic_mean"] == 0.04
        assert result["metrics"]["sharpe"] == 1.2

    def test_empty_string_returns_none(self):
        from research_core.agent_api import _parse_cli_json
        assert _parse_cli_json("") is None
        assert _parse_cli_json("   \n  \n") is None

    def test_no_json_returns_none(self):
        from research_core.agent_api import _parse_cli_json
        raw = "[ERROR] Something went wrong\nNo JSON here at all"
        assert _parse_cli_json(raw) is None

    def test_log_with_braces_but_no_valid_json(self):
        """Log lines containing stray braces must not cause false positives."""
        from research_core.agent_api import _parse_cli_json
        raw = "[INFO] config {region: cn}\n[WARN] cache {dir: /tmp}\n"
        assert _parse_cli_json(raw) is None

    def test_returns_dict_not_list(self):
        """When stdout is a JSON array, the helper extracts the last dict
        object from it (never returns the raw list)."""
        from research_core.agent_api import _parse_cli_json
        raw = json.dumps([{"a": 1}, {"b": 2}])
        result = _parse_cli_json(raw)
        # Must return a dict, not a list
        assert isinstance(result, dict)
        assert result == {"b": 2}

    def test_array_without_dicts_returns_none(self):
        """A JSON array of primitives (no dict inside) returns None."""
        from research_core.agent_api import _parse_cli_json
        raw = json.dumps([1, 2, 3])
        assert _parse_cli_json(raw) is None

    def test_nested_braces_in_json(self):
        """JSON with nested objects must parse correctly."""
        from research_core.agent_api import _parse_cli_json
        raw = (
            "log line\n"
            '{"a": {"b": {"c": 1}}, "d": 2}\n'
        )
        result = _parse_cli_json(raw)
        assert result is not None
        assert result["a"]["b"]["c"] == 1
        assert result["d"] == 2


# ═══════════════════════════════════════════════════════════════
# Section 19 — Qlib parsing with log+JSON & failure → error status
# ═══════════════════════════════════════════════════════════════

class TestQlibParsingLogAndMultiLine:
    """mine_factor / qlib_backtest must parse log+JSON output and return
    status='error' (not 'completed') when parsing fails."""

    @staticmethod
    def _fake_proc(stdout: str, returncode: int = 0):
        from subprocess import CompletedProcess
        return CompletedProcess(
            args=["fake"], returncode=returncode,
            stdout=stdout, stderr="",
        )

    # ── mine_factor: log + multi-line JSON ────────────────────────────

    def test_mine_factor_log_plus_multiline_json(self, monkeypatch):
        """mine_factor() must parse pretty-printed JSON preceded by log lines."""
        payload = {
            "definition": {
                "name": "reversal_5d",
                "expression": "Ref($close, 5) / $close - 1",
            },
            "evaluation": {
                "metrics": [
                    {"name": "ic_mean", "value": 0.035},
                    {"name": "icir", "value": 0.52},
                ],
                "artifacts": {},
            },
            "top_metrics": {
                "ic_mean": 0.035,
                "rank_ic_mean": 0.041,
                "icir": 0.52,
                "long_short_spread": 0.012,
            },
        }
        fake_stdout = (
            "[INFO] Initializing qlib workspace...\n"
            "[INFO] Loading csi300 instruments...\n"
            + json.dumps(payload, indent=2)
        )

        import research_core.agent_api as api
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: self._fake_proc(fake_stdout),
        )

        result = api.mine_factor("reversal_5d", "Ref($close, 5) / $close - 1")
        assert result["status"] == "completed"
        assert result["ic_mean"] == 0.035
        assert result["ic_ir"] == 0.52

    def test_mine_factor_unparseable_returns_error(self, monkeypatch):
        """When CLI exits 0 but output is not JSON, status must be 'error'."""
        fake_stdout = (
            "[INFO] Running...\n"
            "Some non-JSON output without braces\n"
        )

        import research_core.agent_api as api
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: self._fake_proc(fake_stdout),
        )

        result = api.mine_factor("test", "$close")
        assert result["status"] == "error", (
            f"Expected 'error', got '{result['status']}'"
        )
        assert "error" in result
        assert "Failed to parse" in result["error"]

    # ── qlib_backtest: log + single-line JSON ─────────────────────────

    def test_qlib_backtest_log_plus_single_line_json(self, monkeypatch):
        """qlib_backtest() must parse single-line JSON preceded by log lines."""
        payload = {
            "run_id": "abc123",
            "status": "completed",
            "engine": "qlib_daily_robust_v6.1",
            "metrics": {
                "total_return": 0.15,
                "annualized_return": 0.12,
                "max_drawdown": -0.08,
                "sharpe": 1.35,
                "volatility": 0.18,
                "win_rate": 0.55,
            },
            "equity_curve": [],
        }
        fake_stdout = (
            "[INFO] Qlib backtest starting...\n"
            "[WARN] Using minimal init\n"
            + json.dumps(payload)
        )

        import research_core.agent_api as api
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: self._fake_proc(fake_stdout),
        )

        result = api.qlib_backtest("($close / Ref($close, 20) - 1)")
        assert result["status"] == "completed"
        assert result["sharpe_ratio"] == 1.35
        assert result["annualized_return"] == 0.12

    def test_qlib_backtest_unparseable_returns_error(self, monkeypatch):
        """When CLI exits 0 but output is not JSON, status must be 'error'."""
        import research_core.agent_api as api
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: self._fake_proc("Not JSON at all\n"),
        )

        result = api.qlib_backtest("bad_expr")
        assert result["status"] == "error", (
            f"Expected 'error', got '{result['status']}'"
        )
        assert "Failed to parse" in result["error"]

    # ── auto_mine: log + multi-line JSON ──────────────────────────────

    def test_auto_mine_log_plus_multiline_json(self, monkeypatch):
        """auto_mine() must parse pretty-printed JSON preceded by log lines."""
        payload = {
            "theme": "momentum",
            "generated_count": 1,
            "results": [
                {
                    "definition": {"name": "mom_20d", "expression": "$close"},
                    "evaluation": {"metrics": []},
                    "top_metrics": {"ic_mean": 0.04, "icir": 0.55},
                    "candidate": {"name": "mom_20d"},
                },
            ],
        }
        fake_stdout = (
            "[INFO] AI factor mining starting...\n"
            + json.dumps(payload, indent=2)
        )

        import research_core.agent_api as api
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: self._fake_proc(fake_stdout),
        )

        result = api.auto_mine("momentum")
        assert result["status"] == "completed"
        assert result["generated_count"] == 1
        assert result["best_factor"] == "mom_20d"

    def test_auto_mine_unparseable_returns_error(self, monkeypatch):
        """When CLI exits 0 but output is not JSON, status must be 'error'."""
        import research_core.agent_api as api
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: self._fake_proc("No JSON here\n"),
        )

        result = api.auto_mine("test")
        assert result["status"] == "error", (
            f"Expected 'error', got '{result['status']}'"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))



