from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from common.paths import data_path, runtime_path


def now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(slots=True)
class FactorLabWorkspaceConfig:
    data_root: Path = field(default_factory=lambda: data_path("factor_lab"))
    runtime_root: Path = field(default_factory=lambda: runtime_path("factor_lab"))

    def ensure_directories(self) -> dict[str, Path]:
        paths = {
            "data_root": self.data_root,
            "runtime_root": self.runtime_root,
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
