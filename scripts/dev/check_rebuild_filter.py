"""Quick check of rebuild_passing_factors.passing_factor_ids on synthetic input."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from rebuild_passing_factors import passing_factor_ids  # noqa: E402

manifest = {
    "results": [
        {"factor_id": "A:1", "status": "validated", "failed_gates": []},
        {"factor_id": "B:2", "status": "validated", "failed_gates": ["residual_ic"]},
        {"factor_id": "C:3", "status": "rejected", "failed_gates": ["rank_ic"]},
        {"factor_id": "D:4", "status": "validated"},
        {"factor_id": "E:5", "status": "error", "failed_gates": []},
        {"factor_id": "", "status": "validated", "failed_gates": []},
    ]
}
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "m.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    got = passing_factor_ids(path)
    print("passing:", got)
    assert got == ["A:1", "D:4"], got
    print("OK: only validated, gate-clean, non-empty ids pass")
