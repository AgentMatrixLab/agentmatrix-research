from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_disabled_backend_is_explicit_and_independent_of_legacy_config():
    html = (ROOT / "pages/factor-db-dashboard/submissions.html").read_text(encoding="utf-8")
    js = (ROOT / "pages/factor-db-dashboard/submissions.js").read_text(encoding="utf-8")
    config = (ROOT / "pages/factor-db-dashboard/private-config.js").read_text(encoding="utf-8")
    assert "./private-config.js" in html
    assert "../factor-lab-dashboard/config.js" not in html
    assert "PRIVATE_FACTOR_BACKEND_ENABLED = false" in config
    assert "PRIVATE_FACTOR_BACKEND_ENABLED === false" in js
    assert "后端尚未开通" in js


def test_portal_exposes_public_summary_and_backup_without_changing_password():
    html = (ROOT / "pages/index.html").read_text(encoding="utf-8")
    assert "factor-db-dashboard/submissions.html" in html
    assert "factor-db-dashboard/turnover40.html" in html
    assert "https://factor.liangjun.net.cn/factor-lab/" in html
    app = (ROOT / "pages/factor-db-dashboard/app.js").read_text(encoding="utf-8")
    assert 'const ACCESS_PASSWORD = window.FACTORDB_ACCESS_PASSWORD || "factorlab2026"' in app
