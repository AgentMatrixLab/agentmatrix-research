from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class LegacyEngineRunner:
    """Execute Chenxi Engine out of process.

    The legacy integration intentionally replaces the global `config` module.
    Process isolation prevents that behavior from affecting AgentMatrix.
    """

    def __init__(self, engine_root: str | Path, *, timeout_seconds: int = 3600):
        self.engine_root = Path(engine_root).expanduser().resolve()
        self.timeout_seconds = timeout_seconds

    def validate(self) -> None:
        required = [
            self.engine_root / "config.py",
            self.engine_root / "engine" / "desk_adapter.py",
            self.engine_root / "strategies" / "__init__.py",
        ]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Desktop backtest engine is incomplete: {missing}")

    def run(
        self,
        *,
        strategy_name: str,
        start: str,
        end: str,
        capital: float,
        benchmark: str,
        fee_rate: float,
        slippage: float,
        rebalance_freq: int,
        data_dir: str | None = None,
    ) -> dict[str, Any]:
        self.validate()
        worker = Path(__file__).with_name("worker.py")
        request_payload = {
            "engine_root": str(self.engine_root),
            "strategy_name": strategy_name,
            "start": start,
            "end": end,
            "capital": capital,
            "benchmark": benchmark,
            "fee_rate": fee_rate,
            "slippage": slippage,
            "rebalance_freq": rebalance_freq,
            "data_dir": data_dir or "",
        }

        with tempfile.TemporaryDirectory(prefix="agentmatrix-custom-engine-") as temp_dir:
            temp_path = Path(temp_dir)
            artifact_path = temp_path / "artifacts"
            artifact_path.mkdir()
            request_payload["artifact_dir"] = str(artifact_path)
            request_path = temp_path / "request.json"
            result_path = temp_path / "result.json"
            request_path.write_text(json.dumps(request_payload, ensure_ascii=False), encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(worker), str(request_path), str(result_path)],
                cwd=str(self.engine_root),
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise RuntimeError(f"Desktop backtest engine failed: {detail[-2000:]}")
            if not result_path.is_file():
                raise RuntimeError("Desktop backtest engine did not produce a result")
            return json.loads(result_path.read_text(encoding="utf-8"))
