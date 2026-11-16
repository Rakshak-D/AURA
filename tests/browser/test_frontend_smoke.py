"""Real-app Playwright coverage for AURA's browser foundation.

Run with ``AURA_RUN_BROWSER=1 python -m pytest -m browser -q`` after installing
``requirements-dev.txt`` and ``requirements-browser.txt`` and Chromium. Tests
start a real Uvicorn process with disposable SQLite data; the browser guard is
installed before the first page is created and aborts every non-local host.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.getenv("AURA_RUN_BROWSER") != "1",
        reason="browser job is opt-in; install Playwright/Chromium and set AURA_RUN_BROWSER=1",
    ),
]

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_VIEWPORTS = (
    (1440, 900),
    (1024, 768),
    (768, 1024),
    (390, 844),
    (320, 844),
)
NO_MODEL_CHAT_RESPONSE = "No AI model is available right now, so I can't answer general chat messages."
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class BrowserSession:
    base_url: str
    page: object
    context: object
    external_attempts: list[str]
    unauthenticated_data_requests: list[str]
    console_errors: list[str]
    page_errors: list[str]
    encoded_resource_bytes: dict[str, int]
    recording_dir: Path | None = None


@dataclass(repr=False)
class BrowserCredentials:
    identifier: str
    password: str

    def __repr__(self) -> str:
        return "BrowserCredentials(<redacted>)"


def _hostname(url: str) -> str | None:
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def _safe_request_label(url: str) -> str:
    """Keep network evidence useful without writing query credentials to disk."""
    parsed = urlsplit(url)
    host = parsed.hostname or "<invalid-host>"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}{parsed.path}"


def _safe_console_error(message: str) -> str:
    """Redact query strings if a browser error includes a signed URL."""
    return re.sub(
        r"((?:https?|wss?)://[^\s\"'<>?]+)\?[^\s\"'<>]+",
        r"\1?<redacted>",
        message,
    )


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_app(process: subprocess.Popen[bytes], base_url: str, log_path: Path) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "AURA exited before becoming ready. Server log:\n"
                + log_path.read_text(encoding="utf-8", errors="replace")[-12000:]
            )
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    raise RuntimeError(
        "AURA did not become ready. Server log:\n"
        + log_path.read_text(encoding="utf-8", errors="replace")[-12000:]
    )


@pytest.fixture(scope="session")
def aura_server(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Launch the real app with no model and a database isolated to this run."""
    runtime_dir = tmp_path_factory.mktemp("aura-browser-runtime")
    port = _free_local_port()
    base_url = f"http://127.0.0.1:{port}"
    data_dir = runtime_dir / "data"
    data_dir.mkdir()
    log_path = runtime_dir / "uvicorn.log"
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": str(_PROJECT_ROOT),
            "ENVIRONMENT": "development",
            "BASE_DIR": str(_PROJECT_ROOT),
            "DATA_DIR": str(data_dir),
            "DB_PATH": str(data_dir / "aura-browser-test.sqlite3"),
            "DATABASE_URL": "",
            "UPLOADS_DIR": str(data_dir / "uploads"),
            "LOGS_DIR": str(data_dir / "logs"),
            "MODELS_DIR": str(runtime_dir / "models-empty"),
            "CHROMA_PATH": str(runtime_dir / "chroma-empty"),
            "AUTH_SECRET_KEY": secrets.token_urlsafe(48),
            "SECRET_KEY": secrets.token_urlsafe(48),
            "REMINDER_SCHEDULER_ENABLED": "false",
            "HOST": "127.0.0.1",
            "PORT": str(port),
            "ALLOWED_ORIGINS": base_url,
            "LOG_LEVEL": "WARNING",
            "USE_GPU": "false",
        }
    )

    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=_PROJECT_ROOT,
            env=environment,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_app(process, base_url, log_path)
            yield base_url
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


@pytest.fixture(scope="session")
def browser_account(aura_server: str) -> BrowserCredentials:
    """Create one ephemeral account through the actual local auth endpoint."""
    credentials = BrowserCredentials(
        identifier=f"a0-browser-{uuid.uuid4().hex[:12]}@example.test",
        password=secrets.token_urlsafe(24),
    )
    request = urllib.request.Request(
        f"{aura_server}/api/auth/register",
        data=json.dumps(
            {"identifier": credentials.identifier, "password": credentials.password}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 201:
            raise RuntimeError(f"Synthetic browser account registration returned {response.status}")
    return credentials


@pytest.fixture
def browser_session(
    aura_server: str, request: pytest.FixtureRequest, tmp_path: Path
) -> BrowserSession:
    playwright = pytest.importorskip("playwright.sync_api")
    playwright_runtime = playwright.sync_playwright().start()
    browser = playwright_runtime.chromium.launch(headless=True)
    evidence_dir = os.getenv("AURA_BROWSER_EVIDENCE_DIR")
    capture_video = os.getenv("AURA_CAPTURE_VIDEO") == "1" and request.node.name == "test_recorded_user_journey"
    recording_dir: Path | None = None
    context_options: dict[str, object] = {
        "service_workers": "block",
        "viewport": {"width": 1440, "height": 900},
    }
    if capture_video:
        recording_dir = tmp_path / "browser-recording"
        recording_dir.mkdir()
        context_options["record_video_dir"] = str(recording_dir)
        context_options["record_video_size"] = {"width": 1440, "height": 900}

    context = browser.new_context(**context_options)
    external_attempts: list[str] = []
    seen_external: set[str] = set()
    unauthenticated_data_requests: list[str] = []
    console_errors: list[str] = []
    page_errors: list[str] = []
    request_paths: dict[str, str] = {}
    encoded_resource_bytes: dict[str, int] = {}

    def note_external(url: str) -> None:
        label = _safe_request_label(url)
        if label not in seen_external:
            seen_external.add(label)
            external_attempts.append(label)

    def observe_request(browser_request: object) -> None:
        url = browser_request.url
        if _hostname(url) not in _LOCAL_HOSTS:
            note_external(url)

    def guard_http(route: object) -> None:
        url = route.request.url
        if _hostname(url) not in _LOCAL_HOSTS:
            note_external(url)
            route.abort("blockedbyclient")
            return
        route.continue_()

    def guard_websocket(websocket_route: object) -> None:
        if _hostname(websocket_route.url) not in _LOCAL_HOSTS:
            note_external(websocket_route.url)
            websocket_route.close()
            return
        websocket_route.connect_to_server()

    # Register all network controls before creating a page or navigating.
    context.on("request", observe_request)
    context.route("**/*", guard_http)
    context.route_web_socket("**/*", guard_websocket)
    page = context.new_page()
    cdp = context.new_cdp_session(page)
    cdp.send("Network.enable")

    def record_response(event: dict[str, object]) -> None:
        response = event["response"]
        path = urlsplit(response["url"]).path
        if path == "/" or path.startswith("/static/"):
            request_paths[event["requestId"]] = path

    def record_finished(event: dict[str, object]) -> None:
        path = request_paths.get(event["requestId"])
        if path:
            encoded_resource_bytes[path] = int(event["encodedDataLength"])

    cdp.on("Network.responseReceived", record_response)
    cdp.on("Network.loadingFinished", record_finished)
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "response",
        lambda response: unauthenticated_data_requests.append(_safe_request_label(response.url))
        if response.status == 401
        and urlsplit(response.url).path.startswith("/api/")
        and "/auth/" not in urlsplit(response.url).path
        else None,
    )
    page.on(
        "console",
        lambda message: console_errors.append(message.text) if message.type == "error" else None,
    )
    session = BrowserSession(
        base_url=aura_server,
        page=page,
        context=context,
        external_attempts=external_attempts,
        unauthenticated_data_requests=unauthenticated_data_requests,
        console_errors=console_errors,
        page_errors=page_errors,
        encoded_resource_bytes=encoded_resource_bytes,
        recording_dir=recording_dir,
    )
    try:
        yield session
    finally:
        video = page.video
        context.close()
        if video and recording_dir:
            output_dir = Path(evidence_dir) / "recordings" if evidence_dir else Path("tests/browser-artifacts/recordings")
            output_dir.mkdir(parents=True, exist_ok=True)
            video.save_as(str(output_dir / "a0-user-journey.webm"))
        browser.close()
        playwright_runtime.stop()

        if evidence_dir:
            evidence_path = Path(evidence_dir)
            evidence_path.mkdir(parents=True, exist_ok=True)
            summary_path = evidence_path / "browser-run-summary.jsonl"
            with summary_path.open("a", encoding="utf-8") as summary:
                summary.write(
                    json.dumps(
                        {
                            "test": request.node.name,
                            "external_attempts": external_attempts,
                            "unauthenticated_data_requests": unauthenticated_data_requests,
                            "uncaught_javascript_errors": page_errors,
                            "console_errors": [_safe_console_error(error) for error in console_errors],
                        }
                    )
                    + "\n"
                )

        assert not external_attempts, (
            "Browser attempted non-local requests; all were blocked and recorded: "
            + ", ".join(external_attempts)
        )


def _capture(session: BrowserSession, name: str) -> None:
    evidence_dir = os.getenv("AURA_BROWSER_EVIDENCE_DIR")
    if not evidence_dir:
        return
    output_dir = Path(evidence_dir) / "screenshots"
    output_dir.mkdir(parents=True, exist_ok=True)
    session.page.screenshot(path=str(output_dir / name), full_page=True)


def _capture_initial_payload(session: BrowserSession) -> None:
    evidence_dir = os.getenv("AURA_BROWSER_EVIDENCE_DIR")
    if not evidence_dir:
        return

    resources: list[dict[str, object]] = []
    totals: dict[str, dict[str, int]] = {}
    for path, transfer_bytes in sorted(session.encoded_resource_bytes.items()):
        local_path = _PROJECT_ROOT / "frontend" / "index.html" if path == "/" else (
            _PROJECT_ROOT / "frontend" / path.removeprefix("/static/")
        )
        if not local_path.is_file():
            continue
        category = {
            ".html": "html",
            ".css": "css",
            ".js": "javascript",
            ".woff2": "fonts",
        }.get(local_path.suffix, "other")
        body_bytes = local_path.stat().st_size
        category_total = totals.setdefault(category, {"body_bytes": 0, "transfer_bytes": 0})
        category_total["body_bytes"] += body_bytes
        category_total["transfer_bytes"] += transfer_bytes
        resources.append(
            {
                "path": path,
                "category": category,
                "body_bytes": body_bytes,
                "transfer_bytes": transfer_bytes,
            }
        )

    output = {
        "command": "AURA_RUN_BROWSER=1 python -m pytest -m browser -k test_sign_in_and_ui_registration_use_the_real_backend -q",
        "measurement": "Chromium CDP Network.loadingFinished encodedDataLength; local response body sizes from checked-in files",
        "resources": resources,
        "totals": totals,
        "total_body_bytes": sum(item["body_bytes"] for item in resources),
        "total_transfer_bytes": sum(item["transfer_bytes"] for item in resources),
    }
    output_path = Path(evidence_dir) / "payload-measurements.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")


def _assert_no_uncaught_errors(session: BrowserSession) -> None:
    assert not session.page_errors, "Uncaught JavaScript errors: " + " | ".join(session.page_errors)


def _sign_in(session: BrowserSession, credentials: BrowserCredentials) -> None:
    page = session.page
    page.goto(session.base_url, wait_until="domcontentloaded")
    auth_panel = page.locator("#aura-auth-panel")
    auth_panel.wait_for(state="visible")
    page.locator("#aura-auth-identifier").fill(credentials.identifier)
    page.locator("#aura-auth-password").fill(credentials.password)
    page.get_by_role("button", name="Sign in", exact=True).click()
    page.wait_for_function("() => Boolean(sessionStorage.getItem('aura_access_token'))")
    auth_panel.wait_for(state="hidden")
    page.locator(".app-container").wait_for(state="visible")
    signed_in_notice = page.get_by_text("Signed in", exact=True)
    if signed_in_notice.count():
        signed_in_notice.wait_for(state="detached", timeout=4000)


def _assert_active_view(page: object, view_id: str) -> None:
    assert page.locator(f"#view-{view_id}").evaluate(
        "element => element.classList.contains('active')"
    )


def test_sign_in_and_ui_registration_use_the_real_backend(
    browser_session: BrowserSession, browser_account: BrowserCredentials
) -> None:
    page = browser_session.page
    for width, height in ((1440, 900), (1024, 768), (390, 844)):
        page.set_viewport_size({"width": width, "height": height})
        page.goto(browser_session.base_url, wait_until="domcontentloaded")
        page.locator("#aura-auth-panel").wait_for(state="visible")
        if width == 1440:
            page.wait_for_load_state("load")
            page.wait_for_load_state("networkidle")
            _capture_initial_payload(browser_session)
        assert page.locator("#aura-auth-identifier").is_editable()
        assert page.locator("#aura-auth-password").is_editable()
        form_bounds = page.locator("#aura-auth-panel form").bounding_box()
        assert form_bounds is not None
        assert form_bounds["x"] >= 0 and form_bounds["x"] + form_bounds["width"] <= width
        assert form_bounds["y"] >= 0 and form_bounds["y"] + form_bounds["height"] <= height
        _capture(browser_session, f"sign-in-{width}x{height}.png")

    _sign_in(browser_session, browser_account)
    assert not browser_session.unauthenticated_data_requests, (
        "Protected data requests ran without a session: "
        + ", ".join(browser_session.unauthenticated_data_requests)
    )
    _assert_no_uncaught_errors(browser_session)

    # Registration is also exercised in the actual UI, then auto-login uses the
    # real registration and login endpoints in the disposable SQLite database.
    page.evaluate("sessionStorage.removeItem('aura_access_token')")
    page.reload(wait_until="domcontentloaded")
    panel = page.locator("#aura-auth-panel")
    panel.wait_for(state="visible")
    new_credentials = {
        "identifier": f"a0-ui-{uuid.uuid4().hex[:12]}@example.test",
        "password": secrets.token_urlsafe(24),
    }
    page.locator("#aura-auth-identifier").fill(new_credentials["identifier"])
    page.locator("#aura-auth-password").fill(new_credentials["password"])
    page.get_by_role("button", name="Create account", exact=True).click()
    page.wait_for_function("() => Boolean(sessionStorage.getItem('aura_access_token'))")
    panel.wait_for(state="hidden")
    _assert_no_uncaught_errors(browser_session)


def test_missing_local_icon_script_does_not_block_sign_in(
    browser_session: BrowserSession, browser_account: BrowserCredentials
) -> None:
    page = browser_session.page

    def block_icon_file(route: object) -> None:
        route.abort("blockedbyclient")

    # Simulate a locally bundled icon asset failing to load. This route is local
    # and does not exempt the external-network guard.
    browser_session.context.route("**/*lucide*.js*", block_icon_file)
    page.goto(browser_session.base_url, wait_until="domcontentloaded")
    page.locator("#aura-auth-panel").wait_for(state="visible")
    assert page.get_by_role("button", name="Sign in", exact=True).is_visible()

    _sign_in(browser_session, browser_account)
    page.locator(".app-container").wait_for(state="visible")
    for label in ("Tasks", "Chat"):
        navigation_button = page.get_by_role("button", name=label, exact=True)
        assert navigation_button.is_visible()
        navigation_button.click()
        _assert_active_view(page, label.lower())

    assert not browser_session.unauthenticated_data_requests
    assert not browser_session.external_attempts
    _assert_no_uncaught_errors(browser_session)


def test_tasks_create_complete_and_persist_through_the_real_backend(
    browser_session: BrowserSession, browser_account: BrowserCredentials
) -> None:
    _sign_in(browser_session, browser_account)
    page = browser_session.page
    page.get_by_role("button", name="Tasks", exact=True).click()
    _assert_active_view(page, "tasks")
    page.locator("#add-task-btn").click()
    title = f"A0 browser task {uuid.uuid4().hex[:8]}"
    page.locator("#task-title").fill(title)
    page.get_by_role("button", name="Save Task", exact=True).click()

    todo_title = page.locator("#todo-list .task-title").filter(has_text=title)
    todo_title.wait_for(state="visible")
    page.locator("#todo-list .task-checkbox").click()
    done_title = page.locator("#done-list .task-title").filter(has_text=title)
    done_title.wait_for(state="visible")
    page.wait_for_timeout(3200)
    _capture(browser_session, "tasks-1440x900.png")

    page.reload(wait_until="domcontentloaded")
    page.locator("#aura-auth-panel").wait_for(state="hidden")
    assert page.locator("#task-modal.active, #settings-modal.active").count() == 0
    page.get_by_role("button", name="Tasks", exact=True).click()
    page.locator("#done-list .task-title").filter(has_text=title).wait_for(state="visible")
    _assert_no_uncaught_errors(browser_session)


def test_chat_returns_a_real_graceful_no_model_response(
    browser_session: BrowserSession, browser_account: BrowserCredentials
) -> None:
    _sign_in(browser_session, browser_account)
    page = browser_session.page
    chat_responses: list[object] = []
    page.on(
        "response",
        lambda response: chat_responses.append(response)
        if urlsplit(response.url).path == "/api/chat"
        else None,
    )
    page.locator("#chat-input").fill("Please say hello for the A0 browser check.")
    page.locator(".send-btn").click()
    response = page.locator(".message.assistant .message-content").last
    response.wait_for(state="visible", timeout=30000)
    page.wait_for_function(
        "() => !document.querySelector('.message.assistant.loading')"
    )
    response_text = response.inner_text().strip()
    assert response_text == NO_MODEL_CHAT_RESPONSE
    assert chat_responses, "The authenticated Chat API did not return a response."
    api_response = chat_responses[-1]
    assert api_response.status == 200
    api_payload = api_response.json()
    assert api_payload["response"] == NO_MODEL_CHAT_RESPONSE
    assert isinstance(api_payload.get("action_taken"), str)
    assert isinstance(api_payload.get("data"), dict)
    assert isinstance(api_payload.get("suggestions"), list)
    _capture(browser_session, "chat-1440x900.png")

    geometry: list[dict[str, object]] = []
    for width, height in ((390, 844), (320, 844)):
        page.set_viewport_size({"width": width, "height": height})
        page.locator("#chat-history").evaluate(
            "element => { element.scrollTop = element.scrollHeight; }"
        )
        page.wait_for_timeout(350)
        message_bounds = response.bounding_box()
        composer_bounds = page.locator(".input-area").bounding_box()
        history_bounds = page.locator("#chat-history").bounding_box()
        input_geometry = page.locator("#chat-input").evaluate(
            """element => {
                const style = getComputedStyle(element);
                const canvas = document.createElement('canvas');
                const context = canvas.getContext('2d');
                context.font = style.font;
                return {
                    width: element.getBoundingClientRect().width,
                    height: element.getBoundingClientRect().height,
                    available_width: element.clientWidth
                        - parseFloat(style.paddingLeft)
                        - parseFloat(style.paddingRight),
                    placeholder_width: context.measureText(element.placeholder).width,
                };
            }"""
        )
        assert message_bounds is not None
        assert composer_bounds is not None
        assert history_bounds is not None
        message_bottom = message_bounds["y"] + message_bounds["height"]
        assert message_bottom <= composer_bounds["y"], (
            f"Assistant message is obscured by the composer at {width}x{height}: "
            f"message={message_bounds}, composer={composer_bounds}"
        )
        history_bottom = history_bounds["y"] + history_bounds["height"]
        assert history_bounds["y"] <= message_bounds["y"]
        assert message_bottom <= history_bottom
        assert input_geometry["placeholder_width"] <= input_geometry["available_width"], (
            f"Composer placeholder is clipped at {width}x{height}: {input_geometry}"
        )
        assert composer_bounds["x"] >= 0
        assert composer_bounds["x"] + composer_bounds["width"] <= width
        assert composer_bounds["y"] + composer_bounds["height"] <= height
        geometry.append(
            {
                "width": width,
                "height": height,
                "assistant_message": message_bounds,
                "composer": composer_bounds,
                "input": input_geometry,
                "vertical_gap": composer_bounds["y"] - message_bottom,
            }
        )
        _capture(browser_session, f"chat-{width}x{height}.png")

    evidence_dir = os.getenv("AURA_BROWSER_EVIDENCE_DIR")
    if evidence_dir:
        geometry_path = Path(evidence_dir) / "chat-geometry-measurements.json"
        geometry_path.parent.mkdir(parents=True, exist_ok=True)
        geometry_path.write_text(json.dumps(geometry, indent=2), encoding="utf-8")
    _assert_no_uncaught_errors(browser_session)


def test_functional_navigation_and_chart_rendering(
    browser_session: BrowserSession, browser_account: BrowserCredentials
) -> None:
    _sign_in(browser_session, browser_account)
    page = browser_session.page

    for label in ("Chat", "Tasks", "Calendar", "Knowledge", "Insights"):
        page.get_by_role("button", name=label, exact=True).click()
        _assert_active_view(page, label.lower())
        active_nav = page.get_by_role("button", name=label, exact=True)
        assert "active" in (active_nav.get_attribute("class") or "")

    page.wait_for_function(
        "() => window.Chart && Chart.getChart(document.getElementById('activityChart')) "
        "&& Chart.getChart(document.getElementById('priorityChart'))"
    )
    chart_info = page.evaluate(
        "() => ({version: Chart.version, charts: ["
        "Boolean(Chart.getChart(document.getElementById('activityChart'))),"
        "Boolean(Chart.getChart(document.getElementById('priorityChart')))]})"
    )
    assert chart_info["version"]
    assert chart_info["charts"] == [True, True]
    _capture(browser_session, "insights-1440x900.png")

    for dead_label in ("Recents", "Saved", "Projects"):
        assert page.get_by_role("button", name=dead_label, exact=True).count() == 0

    page.get_by_role("button", name="Settings", exact=True).click()
    assert page.locator("#settings-modal").is_visible()
    page.get_by_role("button", name="Cancel", exact=True).click()
    _assert_no_uncaught_errors(browser_session)


def test_layout_keyboard_focus_and_touch_sizing_at_required_viewports(
    browser_session: BrowserSession, browser_account: BrowserCredentials
) -> None:
    _sign_in(browser_session, browser_account)
    page = browser_session.page

    measurements: list[dict[str, object]] = []
    for width, height in _VIEWPORTS:
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(350)
        if width <= 768:
            menu_button = page.locator(".mobile-menu-btn")
            assert menu_button.is_visible()
            menu_button.focus()
            page.keyboard.press("Enter")
            assert menu_button.get_attribute("aria-expanded") == "true"
            page.wait_for_timeout(350)
            nav_target = page.get_by_role("button", name="Tasks", exact=True).bounding_box()
            assert nav_target is not None
            assert nav_target["width"] >= 44
            assert 44 <= nav_target["height"] <= 64
            if width == 390:
                _capture(browser_session, "layout-navigation-open-390x844.png")
        else:
            assert not page.locator(".mobile-menu-btn").is_visible()
        page.get_by_role("button", name="Tasks", exact=True).click()
        if width <= 768:
            assert page.locator(".mobile-menu-btn").get_attribute("aria-expanded") == "false"
        page.wait_for_timeout(350)
        _assert_active_view(page, "tasks")
        geometry = page.evaluate(
            "() => ({width: innerWidth, documentWidth: document.documentElement.scrollWidth, "
            "bodyWidth: document.body.scrollWidth, taskButton: (() => {"
            "const r = document.querySelector('#add-task-btn').getBoundingClientRect(); "
            "return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};"
            "})(), heading: (() => {const r = document.querySelector('#view-tasks h2').getBoundingClientRect(); "
            "return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};})(), mobileMenu: (() => {"
            "const r = document.querySelector('.mobile-menu-btn').getBoundingClientRect(); "
            "return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};})()})"
        )
        measurements.append(geometry)
        assert geometry["documentWidth"] <= width + 1, f"Document overflows at {width}x{height}: {geometry}"
        assert geometry["bodyWidth"] <= width + 1, f"Body overflows at {width}x{height}: {geometry}"
        assert geometry["taskButton"]["left"] >= -1
        assert geometry["taskButton"]["right"] <= width + 1
        assert geometry["taskButton"]["top"] >= -1
        assert geometry["taskButton"]["bottom"] <= height + 1
        if width <= 768:
            assert geometry["taskButton"]["width"] >= 44
            assert geometry["taskButton"]["height"] >= 44
            assert not (
                geometry["mobileMenu"]["left"] < geometry["taskButton"]["right"]
                and geometry["taskButton"]["left"] < geometry["mobileMenu"]["right"]
                and geometry["mobileMenu"]["top"] < geometry["taskButton"]["bottom"]
                and geometry["taskButton"]["top"] < geometry["mobileMenu"]["bottom"]
            ), f"Mobile menu button overlaps the task control at {width}x{height}: {geometry}"
            assert not (
                geometry["mobileMenu"]["left"] < geometry["heading"]["right"]
                and geometry["heading"]["left"] < geometry["mobileMenu"]["right"]
                and geometry["mobileMenu"]["top"] < geometry["heading"]["bottom"]
                and geometry["heading"]["top"] < geometry["mobileMenu"]["bottom"]
            ), f"Mobile menu button overlaps the task heading at {width}x{height}: {geometry}"
        assert geometry["heading"]["left"] >= -1
        assert geometry["heading"]["right"] <= width + 1
        heading = geometry["heading"]
        task_button = geometry["taskButton"]
        assert not (
            heading["left"] < task_button["right"]
            and task_button["left"] < heading["right"]
            and heading["top"] < task_button["bottom"]
            and task_button["top"] < heading["bottom"]
        ), f"Task heading overlaps the primary control at {width}x{height}: {geometry}"
        _capture(browser_session, f"layout-tasks-{width}x{height}.png")

        if width <= 768:
            measurements[-1]["tasks_nav_target"] = {
                "width": nav_target["width"],
                "height": nav_target["height"],
            }

    page.set_viewport_size({"width": 1440, "height": 900})
    page.evaluate("document.activeElement.blur()")
    page.keyboard.press("Tab")
    focus = page.evaluate(
        "() => ({focusVisible: document.activeElement.matches(':focus-visible'), "
        "outlineStyle: getComputedStyle(document.activeElement).outlineStyle, "
        "outlineWidth: getComputedStyle(document.activeElement).outlineWidth})"
    )
    assert focus["focusVisible"], f"Keyboard focus is not visible: {focus}"

    evidence_dir = os.getenv("AURA_BROWSER_EVIDENCE_DIR")
    if evidence_dir:
        path = Path(evidence_dir) / "layout-measurements.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(measurements, indent=2), encoding="utf-8")
    _assert_no_uncaught_errors(browser_session)


def test_recorded_user_journey(
    browser_session: BrowserSession, browser_account: BrowserCredentials
) -> None:
    """One real user journey; optionally recorded when AURA_CAPTURE_VIDEO=1."""
    _sign_in(browser_session, browser_account)
    page = browser_session.page
    page.get_by_role("button", name="Tasks", exact=True).click()
    _assert_active_view(page, "tasks")
    page.locator("#add-task-btn").click()
    title = f"Recorded A0 task {uuid.uuid4().hex[:8]}"
    page.locator("#task-title").fill(title)
    page.get_by_role("button", name="Save Task", exact=True).click()
    page.locator("#todo-list .task-title").filter(has_text=title).wait_for(state="visible")
    page.locator("#todo-list .task-checkbox").click()
    page.locator("#done-list .task-title").filter(has_text=title).wait_for(state="visible")

    page.get_by_role("button", name="Chat", exact=True).click()
    _assert_active_view(page, "chat")
    page.locator("#chat-input").fill("Hello, this is the A0 local chat check.")
    page.locator(".send-btn").click()
    page.wait_for_function(
        "() => document.querySelector('.message.assistant .message-content')?.textContent.trim() "
        "&& !document.querySelector('.message.assistant.loading')",
        timeout=30000,
    )

    page.get_by_role("button", name="Calendar", exact=True).click()
    _assert_active_view(page, "calendar")
    page.get_by_role("button", name="Insights", exact=True).click()
    _assert_active_view(page, "insights")
    for dead_label in ("Recents", "Saved", "Projects"):
        assert page.get_by_role("button", name=dead_label, exact=True).count() == 0
    _assert_no_uncaught_errors(browser_session)
