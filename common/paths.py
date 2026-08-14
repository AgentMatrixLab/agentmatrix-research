from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / 'data'
TEST_DOCS_DIR = REPO_ROOT / 'test_docs'
RUNTIME_DIR = REPO_ROOT / 'runtime'

for path in (DATA_DIR, TEST_DOCS_DIR, RUNTIME_DIR):
    path.mkdir(parents=True, exist_ok=True)

def data_path(*parts):
    return DATA_DIR.joinpath(*parts)

def runtime_path(*parts):
    return RUNTIME_DIR.joinpath(*parts)

def ensure_cross_platform():
    """Normalize path separators and set env vars for cross-platform qlib usage.

    Qlib defaults to platform-native separators which breaks team workflows
    (e.g. Windows ``\\`` vs Linux ``/``). This forces consistent forward-slash
    paths and sets QLIB_DATA_PATH if not already configured.
    """
    import os

    # Ensure consistent path separators in key env vars
    for var in ("QLIB_DATA_PATH", "QLIB_CACHE_DIR", "QLIB_EXP_NAME"):
        val = os.environ.get(var)
        if val is not None:
            os.environ[var] = val.replace("\\", "/")
            # propagate to Path for runtime consistency
            if var == "QLIB_DATA_PATH":
                os.environ.setdefault("QLIB_DATA_URI", os.environ[var])
