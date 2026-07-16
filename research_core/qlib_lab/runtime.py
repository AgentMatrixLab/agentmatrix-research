from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.paths import data_path, runtime_path


REGION_ALIASES = {
    "cn": "cn",
    "us": "us",
}


@dataclass(slots=True)
class QlibWorkspaceConfig:
    provider_uri: str
    region: str = "cn"
    market: str = "csi300"
    benchmark: str = "SH000300"
    freq: str = "day"
    cache_dir: str = ""
    experiment_name: str = "agentmatrix_qlib_lab"
    universe: str = "csi300"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "QlibWorkspaceConfig":
        provider = os.getenv("QLIB_PROVIDER_URI", str(data_path("qlib", "cn_data")))
        return cls(
            provider_uri=provider,
            region=os.getenv("QLIB_REGION", "cn"),
            market=os.getenv("QLIB_MARKET", "csi300"),
            benchmark=os.getenv("QLIB_BENCHMARK", "SH000300"),
            freq=os.getenv("QLIB_FREQ", "day"),
            cache_dir=os.getenv("QLIB_CACHE_DIR", str(runtime_path("qlib", "cache"))),
            experiment_name=os.getenv("QLIB_EXPERIMENT_NAME", "agentmatrix_qlib_lab"),
            universe=os.getenv("QLIB_UNIVERSE", "csi300"),
        )

    def resolved_provider_uri(self) -> str:
        return str(Path(self.provider_uri).expanduser().resolve())

    def resolved_cache_dir(self) -> str:
        raw = self.cache_dir or str(runtime_path("qlib", "cache"))
        return str(Path(raw).expanduser().resolve())

    def resolved_region(self) -> str:
        region = self.region.lower()
        if region not in REGION_ALIASES:
            raise ValueError(f"Unsupported qlib region: {self.region}")
        return REGION_ALIASES[region]

    def ensure_directories(self) -> None:
        Path(self.resolved_provider_uri()).mkdir(parents=True, exist_ok=True)
        Path(self.resolved_cache_dir()).mkdir(parents=True, exist_ok=True)
        runtime_path("qlib", "factors").mkdir(parents=True, exist_ok=True)
        runtime_path("qlib", "evaluations").mkdir(parents=True, exist_ok=True)
        runtime_path("qlib", "backtests").mkdir(parents=True, exist_ok=True)


def qlib_data_download_hint(config: QlibWorkspaceConfig) -> str:
    target_dir = config.resolved_provider_uri()
    return (
        "Install pyqlib and download market data with the official helper, for example:\n"
        f"python scripts/get_data.py qlib_data --target_dir {target_dir} --region {config.resolved_region()}"
    )


def _has_provider_payload(provider_uri: str) -> bool:
    target = Path(provider_uri)
    if not target.exists():
        return False
    return any(target.iterdir())


def init_qlib_workspace(
    config: QlibWorkspaceConfig | None = None,
    *,
    require_package: bool = False,
    require_data: bool = False,
) -> dict[str, Any]:
    config = config or QlibWorkspaceConfig.from_env()
    config.ensure_directories()
    base_payload = {
        "provider_uri": config.resolved_provider_uri(),
        "cache_dir": config.resolved_cache_dir(),
        "region": config.resolved_region(),
        "experiment_name": config.experiment_name,
        "download_hint": qlib_data_download_hint(config),
        "initialized": False,
    }

    if require_data and not _has_provider_payload(config.resolved_provider_uri()):
        raise RuntimeError(
            "Qlib provider data is empty. Download market data first.\n"
            f"{qlib_data_download_hint(config)}"
        )

    try:
        import qlib
        from qlib.config import REG_CN, REG_US
    except ImportError as exc:
        if require_package:
            raise RuntimeError(
                "pyqlib is not installed. Install it with `pip install pyqlib` before using qlib_lab."
            ) from exc
        base_payload["package_ready"] = False
        base_payload["message"] = "Workspace scaffolded. Install pyqlib before running factor evaluation."
        return base_payload

    if not _has_provider_payload(config.resolved_provider_uri()):
        base_payload["package_ready"] = True
        base_payload["message"] = "Workspace scaffolded. Download qlib market data before running factor evaluation."
        return base_payload

    region = REG_CN if config.resolved_region() == "cn" else REG_US
    qlib.init(
        provider_uri=config.resolved_provider_uri(),
        region=region,
        exp_manager={
            "class": "MLflowExpManager",
            "module_path": "qlib.workflow.expm",
            "kwargs": {
                "uri": f"file:{runtime_path('qlib', 'mlruns')}",
                "default_exp_name": config.experiment_name,
            },
        },
    )

    base_payload["package_ready"] = True
    base_payload["initialized"] = True
    base_payload["message"] = "Qlib workspace initialized successfully."
    return base_payload
