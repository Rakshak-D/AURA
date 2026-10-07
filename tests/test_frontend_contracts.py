from pathlib import Path

FRONTEND = Path(__file__).parents[1] / "frontend" / "js"


def read(name):
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_frontend_contract_layer_and_search_shape():
    main = read("main.js")
    search = read("search.js")
    assert "async function apiJson" in main
    assert "data?.tasks" in search
    assert "data?.knowledge" in search
    assert "data.results" not in search


def test_frontend_has_no_fake_stream_and_settings_single_initialization():
    chat = read("chat.js")
    settings = read("settings.js")
    assert "simulateStreaming" not in chat
    assert settings.count("loadSettings();") == 1


def test_external_content_uses_safe_dom_boundaries():
    for name in ("chat.js", "search.js", "upload.js", "tasks.js", "notifications.js"):
        source = read(name)
        assert "innerHTML" not in source
