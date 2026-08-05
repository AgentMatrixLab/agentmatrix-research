"""
Pytest configuration — ensures ``research_core`` is importable in CI / PR
environments where the package is not installed via ``pip install -e .``.

This file is automatically loaded by pytest before test collection.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
