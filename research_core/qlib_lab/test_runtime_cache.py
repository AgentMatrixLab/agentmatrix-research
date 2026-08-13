from __future__ import annotations

import os
import unittest
from pathlib import Path

from common.paths import runtime_path
from research_core.qlib_lab.runtime import DEFAULT_CACHE_DIR, QlibWorkspaceConfig


class QlibRuntimeCacheDefaultTest(unittest.TestCase):
    """The cache_dir default must never be an empty string.

    On Windows, Path("").resolve() returns the current working directory,
    which could be a drive root (e.g. D:\\).  An explicit, safe default
    eliminates this foot-gun and keeps the Python API consistent with the
    CLI (which goes through ``from_env``).
    """

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
        old = os.environ.get("QLIB_CACHE_DIR")
        os.environ["QLIB_CACHE_DIR"] = ""
        try:
            config = QlibWorkspaceConfig.from_env()
        finally:
            if old is None:
                os.environ.pop("QLIB_CACHE_DIR", None)
            else:
                os.environ["QLIB_CACHE_DIR"] = old
        self.assertEqual(config.cache_dir, DEFAULT_CACHE_DIR)
        self.assertTrue(config.cache_dir, "cache_dir must not be empty")

    def test_from_env_with_custom_env_var_respected(self) -> None:
        custom = str(Path("/tmp/custom_qlib_cache"))
        old = os.environ.get("QLIB_CACHE_DIR")
        os.environ["QLIB_CACHE_DIR"] = custom
        try:
            config = QlibWorkspaceConfig.from_env()
        finally:
            if old is None:
                os.environ.pop("QLIB_CACHE_DIR", None)
            else:
                os.environ["QLIB_CACHE_DIR"] = old
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


if __name__ == "__main__":
    unittest.main()
