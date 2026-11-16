from pathlib import Path

FRONTEND_ROOT = Path(__file__).parents[1] / "frontend"
FRONTEND = FRONTEND_ROOT / "js"


def read(name):
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_frontend_contract_layer_and_search_shape():
    main = read("main.js")
    search = read("search.js")
    assert "async function apiJson" in main
    assert "data.tasks" in search
    assert "data.knowledge" in search
    assert "data.results" not in search
    assert "Invalid search response" in search


def test_frontend_has_no_fake_stream_and_settings_single_initialization():
    chat = read("chat.js")
    settings = read("settings.js")
    assert "simulateStreaming" not in chat
    assert settings.count("loadSettings();") == 1
    assert "Invalid tasks response" in read("tasks.js")
    assert "Invalid chat response" in chat
    assert "loadUploadedFiles();" in read("main.js")
    assert "API_REQUEST_TIMEOUT_MS" in read("main.js")


def test_external_content_uses_safe_dom_boundaries():
    for name in ("chat.js", "search.js", "upload.js", "tasks.js", "notifications.js"):
        source = read(name)
        assert "innerHTML" not in source


def test_browser_dependencies_are_self_hosted_and_versioned():
    index = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
    styles = (FRONTEND_ROOT / "css" / "styles.css").read_text(encoding="utf-8")
    browser_code = "\n".join(
        path.read_text(encoding="utf-8") for path in FRONTEND.glob("*.js")
    )

    for remote_host in ("unpkg.com", "cdn.jsdelivr.net", "fonts.googleapis.com"):
        assert remote_host not in index + styles + browser_code
    assert "/static/vendor/lucide-1.73.0/lucide.min.js" in index
    assert "/static/vendor/chart.js-4.6.1/chart.umd.min.js" in index
    assert "Sora Variable" in styles
    assert "Inter" in styles
    assert "JetBrains Mono Variable" in styles
