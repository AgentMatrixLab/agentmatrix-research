"""Root conftest — ensures research_core is importable from any test directory
and runtime/ directories exist before any module-level side-effects run."""

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Pre-create runtime/ subdirectories so that modules which depend on them
# at import time don't crash during test collection.
# NOTE: use os.makedirs (not Path.mkdir) — Python 3.13 pathlib has a
# regression on Windows where mkdir(parents=True) can fail when the
# immediate parent already exists but was created in the same process.
_RUNTIME_SUBDIRS = (
    "runtime",
    "runtime/factor_lab",
    "runtime/strategy_engine",
    "runtime/document_normalizer",
    "runtime/document_normalizer/uploads",
)
for _sub in _RUNTIME_SUBDIRS:
    os.makedirs(str(_PROJECT_ROOT / _sub), exist_ok=True)
