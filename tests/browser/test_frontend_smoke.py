"""Small real-browser smoke/security tests.

The API is a deterministic in-process HTTP mock: browser tests exercise the
actual vanilla frontend without requiring a database, model, GPU, or network.
The CI browser job supplies Playwright and Chromium.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

pytestmark = pytest.mark.browser


class _FrontendMockHandler(BaseHTTPRequestHandler):
    tasks: list[dict] = []

    def _json(self, status: int, payload: object) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        if path == "/api/tasks":
            return self._json(200, self.tasks)
        if path == "/api/settings":
            return self._json(200, {"username": "browser-user", "theme": "dark", "ai_temperature": 0.1})
        if path.startswith("/api/search"):
            return self._json(200, {"tasks": self.tasks, "knowledge": []})
        if path.startswith("/api/insights"):
            return self._json(200, {})
        if path.startswith("/static/"):
            return self._serve_static(path.removeprefix("/static/"))
        if path == "/" or path == "/index.html":
            return self._serve_static("index.html")
        self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        if path in {"/api/auth/register", "/api/auth/login"}:
            return self._json(201 if path.endswith("register") else 200, {"access_token": "browser-test-token"})
        if path == "/api/auth/ws-ticket":
            return self._json(200, {"ticket": "browser-test-ticket"})
        if path == "/api/tasks":
            task = {"id": len(self.tasks) + 1, "completed": False, **body}
            self.tasks.append(task)
            return self._json(201, task)
        if path == "/api/chat":
            return self._json(200, {"response": "Mock response"})
        self._json(404, {"detail": "not found"})

    def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._json(200, {})

    def _serve_static(self, relative: str) -> None:
        root = Path(__file__).resolve().parents[2] / "frontend"
        target = (root / relative).resolve()
        if root not in target.parents and target != root:
            return self._json(404, {"detail": "not found"})
        if not target.is_file():
            return self._json(404, {"detail": "not found"})
        data = target.read_bytes()
        content_type = "text/html" if target.suffix == ".html" else "text/javascript" if target.suffix == ".js" else "text/css"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format: str, *_args: object) -> None:
        return


@pytest.fixture
def frontend_server() -> str:
    _FrontendMockHandler.tasks = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FrontendMockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_browser_auth_task_and_xss_rendering(frontend_server: str) -> None:
    if not os.getenv("AURA_RUN_BROWSER"):
        pytest.skip("browser job is opt-in; install Playwright and set AURA_RUN_BROWSER=1")
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as browser:
        browser_instance = browser.chromium.launch(headless=True)
        context = browser_instance.new_context()
        page = context.new_page()
        try:
            page.route("https://unpkg.com/**", lambda route: route.fulfill(status=200, body="window.lucide={createIcons(){}};"))
            page.route("https://cdn.jsdelivr.net/**", lambda route: route.fulfill(status=200, body="window.Chart=function(){};"))
            page.goto(frontend_server, wait_until="networkidle")
            assert page.locator("#aura-auth-panel").is_visible()

            page.locator("#aura-auth-identifier").fill("browser@example.com")
            page.locator("#aura-auth-password").fill("correct horse battery")
            page.get_by_role("button", name="Create account").click()
            page.wait_for_function("() => sessionStorage.getItem('aura_access_token') === 'browser-test-token'")

            page.get_by_role("button", name="Tasks", exact=True).click()
            page.get_by_role("button", name="+ New Task").click()
            page.locator("#task-title").fill("<img src=x onerror=alert(1)>")
            page.get_by_role("button", name="Save Task").click()
            page.locator(".task-title").wait_for()
            title = page.locator(".task-title").first
            assert title.text_content() == "<img src=x onerror=alert(1)>"
            assert page.locator(".task-title img").count() == 0
            assert page.locator("[onerror]").count() == 0
        except Exception:
            artifact_dir = Path("tests/browser-artifacts")
            artifact_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(artifact_dir / "frontend-smoke-failure.png"), full_page=True)
            raise
        finally:
            context.close()
            browser_instance.close()
