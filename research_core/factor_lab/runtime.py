from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from common.paths import data_path, runtime_path


def now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# Explicit, safe fallback cache directory under the repo runtime tree.
# This is used only when *both* the caller passed an empty string/None for
# ``cache_dir`` AND the config's ``runtime_root`` is somehow unusable.
# Never rely on Path("") -> CWD which on Windows could land at D:\.
_FALLBACK_FACTOR_LAB_CACHE_DIR = str(runtime_path("factor_lab", "cache"))


@dataclass(slots=True)
class FactorLabWorkspaceConfig:
    data_root: Path = field(default_factory=lambda: data_path("factor_lab"))
    runtime_root: Path = field(default_factory=lambda: runtime_path("factor_lab"))
    # Market-data cache used by the explore() pipeline.
    #
    # Semantics:
    #   * ``None`` (default) → ``<runtime_root>/cache``.  This keeps callers
    #     that only override ``runtime_root`` (e.g. integration tests wiring
    #     everything under ``tmp_path``) fully contained — the cache dir
    #     implicitly follows the runtime root instead of escaping to the
    #     global project tree.
    #   * ``""`` (empty string) → same fallback as ``None``; kept so callers
    #     passing argparse defaults or "explicitly not set" still behave safely.
    #   * non-empty string → exact user path, used verbatim (via resolve()).
    #   * Environment ``FACTOR_LAB_CACHE_DIR`` → overrides (see ``from_env``).
    cache_dir: Optional[str] = None

    @classmethod
    def from_env(cls) -> "FactorLabWorkspaceConfig":
        """Build a config mirroring what the CLI layer (argparse) produces.

        Callers that must stay in sync with the CLI defaults go through this
        constructor (including agent-api integration tests).
        """
        env_cache = os.getenv("FACTOR_LAB_CACHE_DIR")
        # None / "" both mean "fall back to runtime_root/cache"; an explicit
        # non-empty env var is used verbatim.  This keeps behavior identical
        # to direct construction.
        return cls(cache_dir=env_cache if env_cache else None)

    def resolved_cache_dir(self) -> str:
        """Return an absolute, non-empty cache directory path.

        Resolution order:
        1. ``self.cache_dir`` if non-empty;
        2. ``self.runtime_root / "cache"`` (default, follows runtime_root);
        3. ``_FALLBACK_FACTOR_LAB_CACHE_DIR`` only when runtime_root is
           somehow empty (must never happen).
        """
        raw = self.cache_dir
        if raw:
            return str(Path(raw).expanduser().resolve())
        if self.runtime_root:
            return str(Path(self.runtime_root).expanduser().resolve() / "cache")
        return str(Path(_FALLBACK_FACTOR_LAB_CACHE_DIR).expanduser().resolve())

    def ensure_directories(self) -> dict[str, Path]:
        cache_path = Path(self.resolved_cache_dir())
        paths = {
            "data_root": self.data_root,
            "runtime_root": self.runtime_root,
            "cache_dir": cache_path,
            "specs_dir": self.runtime_root / "specs",
            "catalogs_dir": self.runtime_root / "catalogs",
            "proofs_dir": self.runtime_root / "proofs",
            "reports_dir": self.runtime_root / "reports",
            "jobs_dir": self.runtime_root / "jobs",
            "frames_dir": self.runtime_root / "frames",
            "samples_dir": self.runtime_root / "samples",
            "truth_dir": self.runtime_root / "truth",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        return paths

    def catalog_path(self, library: str) -> Path:
        return self.runtime_root / "catalogs" / f"{library.lower()}_catalog.json"

    def specs_path(self, library: str) -> Path:
        return self.runtime_root / "specs" / f"{library.lower()}_specs.json"

    def proof_path(self, library: str, factor_name: str) -> Path:
        return self.runtime_root / "proofs" / f"{library.lower()}_{factor_name.lower()}_proof.json"

    def report_path(self, name: str, suffix: str = ".md") -> Path:
        return self.runtime_root / "reports" / f"{name}{suffix}"

    def frame_path(self, library: str, name: str, suffix: str = ".csv") -> Path:
        return self.runtime_root / "frames" / f"{library.lower()}_{name}{suffix}"

    def sample_path(self, library: str, factor_name: str, suffix: str = ".json") -> Path:
        return self.runtime_root / "samples" / f"{library.lower()}_{factor_name.lower()}_samples{suffix}"

    def truth_path(self, library: str, factor_name: str, suffix: str = ".json") -> Path:
        return self.runtime_root / "truth" / f"{library.lower()}_{factor_name.lower()}_truth_compare{suffix}"

    def job_path(self, job_id: str) -> Path:
        return self.runtime_root / "jobs" / f"{job_id}.json"
