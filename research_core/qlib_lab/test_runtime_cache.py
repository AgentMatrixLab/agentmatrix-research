from __future__ import annotations

import os
import unittest
from pathlib import Path

from common.paths import runtime_path
from research_core.factor_lab.runtime import FactorLabWorkspaceConfig
from research_core.qlib_lab.runtime import DEFAULT_CACHE_DIR, QlibWorkspaceConfig


class QlibRuntimeCacheDefaultTest(unittest.TestCase):
    """The cache_dir default must never be an empty string.

    On Windows, Path("").resolve() returns the current working directory,
    which could be a drive root (e.g. D:\\).  An explicit, safe default
    eliminates this foot-gun and keeps the Python API consistent with the
    CLI (which goes through ``from_env``).

    Environment variables are snapshotted in setUp() and fully restored in
    tearDown() so tests that mutate ``QLIB_CACHE_DIR`` never leak state.
    """

    def setUp(self) -> None:
        # Preserve the real environment value (may be None = unset).
        self._saved_qlib_cache_dir = os.environ.get("QLIB_CACHE_DIR")

    def tearDown(self) -> None:
        if self._saved_qlib_cache_dir is None:
            os.environ.pop("QLIB_CACHE_DIR", None)
        else:
            os.environ["QLIB_CACHE_DIR"] = self._saved_qlib_cache_dir

    # ── DEFAULT_CACHE_DIR constant ────────────────────────────────────

    def test_default_cache_dir_is_non_empty(self) -> None:
        self.assertTrue(DEFAULT_CACHE_DIR, "DEFAULT_CACHE_DIR must not be empty")

    def test_default_cache_dir_is_under_runtime(self) -> None:
        expected = str(runtime_path("qlib", "cache"))
        self.assertEqual(DEFAULT_CACHE_DIR, expected)

    def test_default_cache_dir_resolves_to_absolute(self) -> None:
        resolved = str(Path(DEFAULT_CACHE_DIR).resolve())
        # Must be an absolute path, not a bare drive letter like "D:\\"
        self.assertTrue(Path(resolved).is_absolute())
        self.assertNotEqual(resolved, str(Path().resolve()))  # not CWD

    # ── Dataclass default (Python API path) ───────────────────────────

    def test_dataclass_default_cache_dir_is_not_empty(self) -> None:
        """Direct construction (Python API) must give a non-empty cache_dir."""
        config = QlibWorkspaceConfig(provider_uri="/tmp/qlib_data")
        self.assertTrue(config.cache_dir, "cache_dir default must not be empty")
        self.assertEqual(config.cache_dir, DEFAULT_CACHE_DIR)

    def test_dataclass_default_matches_from_env(self) -> None:
        """Python API and CLI (from_env) must produce the same default."""
        direct = QlibWorkspaceConfig(provider_uri="/tmp/qlib_data")
        env = QlibWorkspaceConfig.from_env()
        self.assertEqual(direct.cache_dir, env.cache_dir)

    # ── from_env with empty / unset QLIB_CACHE_DIR ────────────────────

    def test_from_env_without_env_var_uses_default(self) -> None:
        os.environ.pop("QLIB_CACHE_DIR", None)
        config = QlibWorkspaceConfig.from_env()
        self.assertEqual(config.cache_dir, DEFAULT_CACHE_DIR)

    def test_from_env_with_empty_env_var_falls_back(self) -> None:
        """QLIB_CACHE_DIR='' must fall back to the safe default, not stay empty."""
        os.environ["QLIB_CACHE_DIR"] = ""
        config = QlibWorkspaceConfig.from_env()
        self.assertEqual(config.cache_dir, DEFAULT_CACHE_DIR)
        self.assertTrue(config.cache_dir, "cache_dir must not be empty")

    def test_from_env_with_custom_env_var_respected(self) -> None:
        custom = str(Path("/tmp/custom_qlib_cache"))
        os.environ["QLIB_CACHE_DIR"] = custom
        config = QlibWorkspaceConfig.from_env()
        self.assertEqual(config.cache_dir, custom)

    # ── resolved_cache_dir never returns empty or drive root ──────────

    def test_resolved_cache_dir_not_empty_for_default(self) -> None:
        config = QlibWorkspaceConfig(provider_uri="/tmp/qlib_data")
        resolved = config.resolved_cache_dir()
        self.assertTrue(resolved, "resolved_cache_dir must not be empty")

    def test_resolved_cache_dir_not_empty_when_cache_dir_blank(self) -> None:
        """Even if someone forces cache_dir='', resolved_cache_dir must
        fall back to the safe default."""
        config = QlibWorkspaceConfig(provider_uri="/tmp/qlib_data", cache_dir="")
        resolved = config.resolved_cache_dir()
        self.assertTrue(resolved, "resolved_cache_dir must not be empty")
        self.assertNotEqual(resolved, str(Path().resolve()))  # not CWD

    def test_resolved_cache_dir_is_absolute(self) -> None:
        config = QlibWorkspaceConfig(provider_uri="/tmp/qlib_data")
        resolved = config.resolved_cache_dir()
        self.assertTrue(Path(resolved).is_absolute())


class FactorLabCacheDefaultTest(unittest.TestCase):
    """FactorLab explore() default cache_dir must be safe and consistent.

    The same rules as Qlib apply: never rely on Path("")->CWD on Windows.
    Python API (explore_factors), CLI entrypoints, and the raw pipeline
    ``explore()`` function must all converge on the same project-runtime
    default (``runtime/factor_lab/cache``).
    """

    def setUp(self) -> None:
        self._saved_fl_cache_dir = os.environ.get("FACTOR_LAB_CACHE_DIR")

    def tearDown(self) -> None:
        if self._saved_fl_cache_dir is None:
            os.environ.pop("FACTOR_LAB_CACHE_DIR", None)
        else:
            os.environ["FACTOR_LAB_CACHE_DIR"] = self._saved_fl_cache_dir

    # ── Cache dir *follows* runtime_root by default ───────────────────
    #
    # This is the crucial regression guard.  Callers such as integration
    # tests build ``FactorLabWorkspaceConfig(runtime_root=tmp_path / ...)``
    # and expect *every* directory the pipeline touches to live under that
    # runtime_root.  If the cache dir escapes to a global project constant
    # it pollutes the real workspace and/or fails on read-only sandboxes.

    def test_default_cache_dir_follows_runtime_root(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            runtime_root = Path(tmp) / "rt"
            config = FactorLabWorkspaceConfig(runtime_root=runtime_root)
            resolved = config.resolved_cache_dir()
            # Must resolve to <runtime_root>/cache
            self.assertEqual(
                Path(resolved).resolve(),
                (runtime_root / "cache").resolve(),
            )

    def test_runtime_root_override_cache_dir_escapes_not_default(self) -> None:
        """Same regression guard as above, with data_root + runtime_root only
        (this is exactly the pattern used by test_alpha_pipeline.py and
        TestExploreBuildPackageE2E setup fixtures)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            config = FactorLabWorkspaceConfig(
                data_root=Path(tmp) / "data",
                runtime_root=Path(tmp) / "runtime",
            )
            resolved = Path(config.resolved_cache_dir()).resolve()
            expected = (Path(tmp) / "runtime" / "cache").resolve()
            self.assertEqual(resolved, expected)
            # Must NOT bleed into the real project's runtime root
            global_rt = runtime_path("factor_lab")
            self.assertNotEqual(resolved, (global_rt / "cache").resolve())

    def test_default_dataclass_cache_dir_field_is_none(self) -> None:
        """The raw ``cache_dir`` slot defaults to ``None`` so
        ``resolved_cache_dir`` can compute it relative to runtime_root."""
        config = FactorLabWorkspaceConfig()
        self.assertIsNone(config.cache_dir)

    def test_resolved_cache_dir_for_default_global_runtime(self) -> None:
        """No runtime_root override → resolves under the global runtime."""
        config = FactorLabWorkspaceConfig()
        resolved = Path(config.resolved_cache_dir()).resolve()
        expected = (runtime_path("factor_lab") / "cache").resolve()
        self.assertEqual(resolved, expected)

    def test_resolved_cache_dir_not_cwd(self) -> None:
        config = FactorLabWorkspaceConfig()
        resolved = config.resolved_cache_dir()
        self.assertNotEqual(resolved, str(Path().resolve()))
        self.assertTrue(Path(resolved).is_absolute())

    # ── Dataclass default == from_env default (Python API ↔ CLI) ──────

    def test_dataclass_default_matches_from_env(self) -> None:
        direct = FactorLabWorkspaceConfig()
        env = FactorLabWorkspaceConfig.from_env()
        self.assertEqual(direct.cache_dir, env.cache_dir)  # both None
        self.assertEqual(
            direct.resolved_cache_dir(), env.resolved_cache_dir()
        )

    # ── from_env with empty / unset FACTOR_LAB_CACHE_DIR ───────────────

    def test_from_env_without_env_var_follows_runtime_root(self) -> None:
        import tempfile
        os.environ.pop("FACTOR_LAB_CACHE_DIR", None)
        with tempfile.TemporaryDirectory() as tmp:
            rt = Path(tmp) / "rt"
            # Can't pass runtime_root via from_env; simulate that even
            # when someone overrides the constructed config's runtime_root
            # afterwards, resolved_cache_dir() is still computed correctly.
            config = FactorLabWorkspaceConfig.from_env()
            object.__setattr__(config, "runtime_root", rt)
            self.assertEqual(
                Path(config.resolved_cache_dir()).resolve(),
                (rt / "cache").resolve(),
            )

    def test_from_env_with_empty_env_var_falls_back(self) -> None:
        """FACTOR_LAB_CACHE_DIR='' must behave identically to None."""
        os.environ["FACTOR_LAB_CACHE_DIR"] = ""
        config = FactorLabWorkspaceConfig.from_env()
        self.assertIsNone(config.cache_dir)  # treated same as unset

    def test_from_env_with_custom_env_var_respected(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            custom = str(Path(tmp) / "custom_fl_cache")
            os.environ["FACTOR_LAB_CACHE_DIR"] = custom
            config = FactorLabWorkspaceConfig.from_env()
            self.assertEqual(config.cache_dir, custom)
            self.assertEqual(
                Path(config.resolved_cache_dir()).resolve(),
                Path(custom).resolve(),
            )

    # ── Explicit cache_dir string always wins ──────────────────────────

    def test_explicit_cache_dir_wins_over_runtime_root(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            explicit = Path(tmp) / "explicit"
            config = FactorLabWorkspaceConfig(
                runtime_root=Path(tmp) / "other_rt",
                cache_dir=str(explicit),
            )
            self.assertEqual(
                Path(config.resolved_cache_dir()).resolve(),
                explicit.resolve(),
            )

    # ── resolved_cache_dir never returns empty or CWD ──────────────────

    def test_resolved_cache_dir_not_empty_when_cache_dir_blank(self) -> None:
        config = FactorLabWorkspaceConfig(cache_dir="")
        resolved = config.resolved_cache_dir()
        self.assertTrue(resolved, "resolved_cache_dir must not be empty")
        self.assertNotEqual(resolved, str(Path().resolve()))  # not CWD

    def test_resolved_cache_dir_is_absolute(self) -> None:
        config = FactorLabWorkspaceConfig()
        resolved = config.resolved_cache_dir()
        self.assertTrue(Path(resolved).is_absolute())

    def test_ensure_directories_creates_cache_dir_under_runtime_root(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            config = FactorLabWorkspaceConfig(
                data_root=Path(tmp) / "data",
                runtime_root=Path(tmp) / "rt",
            )
            created = config.ensure_directories()
            self.assertIn("cache_dir", created)
            self.assertTrue(created["cache_dir"].is_dir())
            self.assertEqual(
                created["cache_dir"].resolve(),
                (Path(tmp) / "rt" / "cache").resolve(),
            )


if __name__ == "__main__":
    unittest.main()
