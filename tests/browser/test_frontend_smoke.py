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
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import uvicorn
from sqlalchemy.orm import sessionmaker

from backend.app import main
from backend.app.providers.secret_store import MasterKeyMaterial, SecretStore
from backend.app.providers.service import ProviderService, get_provider_service

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


@dataclass(repr=False)
class BrowserSession:
    application: "BrowserApplication"
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
class BrowserApplication:
    base_url: str
    provider_transport: object
    session_factory: sessionmaker
    startup_ms: float


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


def _wait_for_app(base_url: str, server_thread: threading.Thread) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if not server_thread.is_alive():
            raise RuntimeError("The AURA test server exited before becoming ready.")
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    raise RuntimeError("AURA did not become ready within the server startup limit.")


class BrowserKeyProtector:
    """Synthetic test-only protector; no real OS vault or key is accessed."""

    _key = b"B" * 32

    def active_key(self) -> MasterKeyMaterial:
        return MasterKeyMaterial("browser-synthetic-key", self._key)

    def load_key(self, key_id: str) -> bytes | None:
        return self._key if key_id == "browser-synthetic-key" else None

    def create_key(self) -> MasterKeyMaterial:
        return self.active_key()


@pytest.fixture
def aura_server(isolated_runtime, synthetic_provider_transport) -> BrowserApplication:
    """Serve the real FastAPI app with isolated SQLite and fake upstream I/O."""
    from backend.app.models.llm_models import llm

    port = _free_local_port()
    base_url = f"http://127.0.0.1:{port}"
    service = ProviderService(
        transport=synthetic_provider_transport,
        secret_store=SecretStore(BrowserKeyProtector()),
    )
    main.app.dependency_overrides[get_provider_service] = lambda: service
    server = uvicorn.Server(
        uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, name="aura-browser-server", daemon=True)
    startup_started = time.perf_counter()
    thread.start()
    try:
        _wait_for_app(base_url, thread)
        startup_ms = (time.perf_counter() - startup_started) * 1000
        if llm.llm is not None or llm.embedding_model is not None or llm._llm_attempted or llm._embedding_attempted:
            raise AssertionError("A model initialized during model-free application startup.")
        yield BrowserApplication(
            base_url,
            synthetic_provider_transport,
            isolated_runtime,
            startup_ms,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        main.app.dependency_overrides.pop(get_provider_service, None)
        if thread.is_alive():
            raise RuntimeError("The AURA browser test server did not shut down cleanly.")


@pytest.fixture
def browser_account(aura_server: BrowserApplication) -> BrowserCredentials:
    """Create one ephemeral account through the actual local auth endpoint."""
    credentials = BrowserCredentials(
        identifier=f"a0-browser-{uuid.uuid4().hex[:12]}@example.test",
        password=secrets.token_urlsafe(24),
    )
    request = urllib.request.Request(
        f"{aura_server.base_url}/api/auth/register",
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
    aura_server: BrowserApplication, request: pytest.FixtureRequest, tmp_path: Path
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
        application=aura_server,
        base_url=aura_server.base_url,
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
            video.save_as(str(output_dir / "a1g-models-streaming-journey.webm"))
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
    session.page.wait_for_function(
        "() => ![...document.body.children].some(element => "
        "element.style.zIndex === '1000' && element.style.animation.includes('slideIn'))"
    )
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


def _open_models(page: object) -> None:
    menu = page.locator(".mobile-menu-btn")
    if menu.is_visible() and not page.locator("#sidebar").evaluate(
        "element => element.classList.contains('open')"
    ):
        menu.click()
    settings_button = page.get_by_role("button", name="Settings", exact=True)
    if menu.is_visible():
        settings_button.focus()
        page.keyboard.press("Enter")
    else:
        settings_button.click()
    page.locator("#settings-modal.active").wait_for(state="visible")
    page.get_by_role("tab", name="Models", exact=True).click()


def _add_connection(
    page: object,
    name: str,
    provider_type: str,
    base_url: str,
    *,
    api_key: str = "",
    token_parameter: str = "max_tokens",
    keyboard: bool = False,
) -> object:
    add_button = page.get_by_role("button", name="Add connection", exact=True)
    if keyboard:
        add_button.focus()
        page.keyboard.press("Enter")
    else:
        add_button.click()
    form = page.locator("#connection-form")
    form.wait_for(state="visible")
    if keyboard:
        assert page.locator("#connection-provider").input_value() == provider_type
    else:
        page.locator("#connection-provider").select_option(provider_type)
    if keyboard:
        assert page.evaluate("() => document.activeElement.id") == "connection-name"
        page.keyboard.type(name)
        page.keyboard.press("Tab")
        page.keyboard.type(base_url)
        page.keyboard.press("Tab")
        assert page.evaluate("() => document.activeElement.textContent.trim()") == "Save connection"
        page.keyboard.press("Enter")
    else:
        page.locator("#connection-name").fill(name)
        page.locator("#connection-url").fill(base_url)
    if provider_type == "openai_compatible":
        page.locator("#token-parameter").select_option(token_parameter)
        if api_key:
            page.locator("#connection-key").fill(api_key)
    if not keyboard:
        page.get_by_role("button", name="Save connection", exact=True).click()
    row = page.locator(".connection-row").filter(has_text=name)
    row.wait_for(state="visible")
    return row


def _set_model_role(
    page: object,
    role: str,
    connection_id: str,
    model_id: str,
    *,
    discovered: bool,
    keyboard: bool = False,
) -> None:
    if keyboard:
        role_select = page.locator("#role-name")
        role_select.focus()
        page.keyboard.press("Home")
        page.keyboard.press("Enter")
        connection_select = page.locator("#role-connection")
        connection_select.focus()
        page.keyboard.press("ArrowDown")
        model_select = page.locator("#role-model")
        model_select.focus()
        page.keyboard.press("ArrowDown")
        assert connection_select.input_value() == connection_id
        assert model_select.input_value() == model_id
    else:
        page.locator("#role-name").select_option(role)
        page.locator("#role-connection").select_option(connection_id)
    if discovered:
        if not keyboard:
            page.locator("#role-model").select_option(model_id)
        page.locator("#role-model-manual").fill("")
    else:
        page.locator("#role-model-manual").fill(model_id)
    save_role = page.get_by_role("button", name="Save role", exact=True)
    if keyboard:
        save_role.focus()
        page.keyboard.press("Enter")
    else:
        save_role.click()
    page.wait_for_function(
        "({role, model}) => [...document.querySelectorAll('.role-summary-row')].some(row => "
        "row.querySelector('.role-label')?.textContent.trim().toLowerCase() === role && "
        "row.querySelector('.role-value')?.textContent.includes(model))",
        arg={"role": role, "model": model_id},
    )


def _assistant_history_count(session: BrowserSession) -> int:
    from backend.app.models.sql_models import ChatHistory

    with session.application.session_factory() as db:
        return db.query(ChatHistory).filter(ChatHistory.role == "assistant").count()


def _clear_test_rate_limit_state() -> None:
    """Keep the multi-scenario browser journey independent of the 5/minute gate."""
    from backend.app.utils.security import limiter

    if hasattr(limiter, "_storage"):
        limiter._storage.reset()


def _wait_for_layout_transition(page: object, width: int) -> None:
    page.wait_for_function(
        "width => { const app = document.querySelector('.app-container').getBoundingClientRect(); "
        "const composer = document.querySelector('.input-area').getBoundingClientRect(); "
        "return app.width <= width + 1 && composer.right <= width + 1; }",
        arg=width,
    )


def _contrast_failures(page: object, selector: str) -> list[dict[str, object]]:
    return page.evaluate(
        """selector => {
            const root = document.querySelector(selector);
            const parse = value => {
                const parts = value.match(/[\\d.]+/g)?.map(Number);
                if (!parts || parts.length < 3) return null;
                return {rgb: parts.slice(0, 3), alpha: parts.length > 3 ? parts[3] : 1};
            };
            const composite = (top, bottom) => top.rgb.map((value, index) =>
                value * top.alpha + bottom[index] * (1 - top.alpha)
            );
            const luminance = rgb => {
                const channels = rgb.map(value => value / 255).map(value =>
                    value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
                );
                return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
            };
            const failures = [];
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                const node = walker.currentNode;
                const text = node.textContent.trim();
                const element = node.parentElement;
                if (!text || !element || element.closest('.visually-hidden, [aria-hidden="true"]')
                    || !element.getClientRects().length) continue;
                const ancestors = [];
                for (let current = element; current; current = current.parentElement) ancestors.push(current);
                let background = [255, 255, 255];
                for (const current of ancestors.reverse()) {
                    const layer = parse(getComputedStyle(current).backgroundColor);
                    if (layer && layer.alpha > 0) background = composite(layer, background);
                }
                const foreground = parse(getComputedStyle(element).color);
                if (!foreground) continue;
                const shown = composite(foreground, background);
                const values = [luminance(shown), luminance(background)].sort((a, b) => b - a);
                const ratio = (values[0] + 0.05) / (values[1] + 0.05);
                if (ratio < 4.5) failures.push({text: text.slice(0, 60), ratio: Number(ratio.toFixed(2))});
            }
            return failures;
        }""",
        selector,
    )


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
        if urlsplit(response.url).path == "/api/chat/stream"
        else None,
    )
    page.locator("#chat-input").fill("Please say hello for the A0 browser check.")
    page.locator(".send-btn").click()
    response = page.locator(".message.assistant .message-content").last
    page.wait_for_function(
        "expected => [...document.querySelectorAll('.message.assistant .message-content')]"
        ".some(element => element.textContent.trim() === expected)",
        arg=NO_MODEL_CHAT_RESPONSE,
        timeout=30000,
    )
    response_text = response.inner_text().strip()
    assert response_text == NO_MODEL_CHAT_RESPONSE
    assert chat_responses, "The authenticated Chat API did not return a response."
    api_response = chat_responses[-1]
    assert api_response.status == 200
    assert "text/event-stream" in api_response.headers.get("content-type", "")
    stream_body = api_response.text()
    assert "event: failed" in stream_body
    assert '"code":"no_model_available"' in stream_body
    assert NO_MODEL_CHAT_RESPONSE in stream_body
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
    page.get_by_role("button", name="Close settings", exact=True).click()
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


def test_a1g_models_and_streaming_regressions(
    browser_session: BrowserSession, browser_account: BrowserCredentials
) -> None:
    """Exercise Settings, secrets, privacy, roles and Chat in the real app."""
    from backend.app.models.sql_models import ChatHistory

    _sign_in(browser_session, browser_account)
    page = browser_session.page
    transport = browser_session.application.provider_transport
    measurements: dict[str, object] = {
        "local_test_application_startup_ms": round(browser_session.application.startup_ms, 2),
        "startup_models_initialized": False,
    }
    page.on("dialog", lambda dialog: dialog.accept())

    settings_started = time.perf_counter()
    _open_models(page)
    page.locator(".connections-empty").wait_for(state="visible")
    measurements["models_initial_render_ms"] = round((time.perf_counter() - settings_started) * 1000, 2)
    assert page.locator("#local-only-toggle").is_checked()
    assert "On" in page.locator("#local-only-state").inner_text()
    assert page.locator("#chat-model-indicator").inner_text() == "No Chat model selected"
    assert page.locator(".role-summary-row .role-value").all_inner_texts() == [
        "Not selected",
        "Not selected",
        "Not selected",
    ]
    _capture(browser_session, "a1g-models-empty-desktop.png")

    local = _add_connection(
        page,
        "Studio Ollama",
        "ollama",
        "http://127.0.0.1:11434",
        keyboard=True,
    )
    local_id = local.get_attribute("data-connection-id")
    assert local_id
    test_started = time.perf_counter()
    local.get_by_role("button", name="Test", exact=True).click()
    local.locator(".connection-state").filter(has_text="Connected").wait_for(state="visible")
    measurements["local_connection_test_ms"] = round((time.perf_counter() - test_started) * 1000, 2)
    listing_started = time.perf_counter()
    local.get_by_role("button", name="Discover models", exact=True).click()
    page.locator("#role-model option[value='qwen2.5:latest']").wait_for(state="attached")
    measurements["synthetic_model_listing_ms"] = round((time.perf_counter() - listing_started) * 1000, 2)
    _capture(browser_session, "a1g-models-ollama-connected.png")

    page.locator("#role-connection").select_option(local_id)
    page.locator("#role-model").select_option("qwen2.5:latest")
    page.get_by_role("button", name="Check capabilities", exact=True).click()
    page.locator("#capability-panel").get_by_text("provider metadata", exact=False).first.wait_for(state="visible")
    assert "unsupported" in page.locator("#capability-panel").inner_text()
    assert "unknown" in page.locator("#capability-panel").inner_text()
    page.locator("#role-connection").select_option("")
    page.locator("#role-model").select_option("")
    _set_model_role(page, "chat", local_id, "qwen2.5:latest", discovered=True, keyboard=True)
    _set_model_role(page, "router", local_id, "qwen2.5:latest", discovered=True)
    assert "Studio Ollama · qwen2.5:latest" in page.locator("#role-summary").inner_text()
    _capture(browser_session, "a1g-models-role-selections.png")

    synthetic_key = "SYNTHETIC_BROWSER_API_KEY_SENTINEL"
    remote_a = _add_connection(
        page,
        "Remote Alpha",
        "openai_compatible",
        "https://api.example.test/v1",
        api_key=synthetic_key,
    )
    remote_a_id = remote_a.get_attribute("data-connection-id")
    assert remote_a_id
    assert page.locator("#connection-key").input_value() == ""
    calls_before_block = len(transport.requests)
    remote_a.get_by_role("button", name="Test", exact=True).click()
    remote_a.locator(".connection-state").filter(has_text="Blocked by Local only").wait_for(state="visible")
    assert len(transport.requests) == calls_before_block
    _capture(browser_session, "a1g-models-cloud-blocked.png")

    remote_a.get_by_role("button", name="Edit", exact=True).click()
    page.locator("#connection-url").fill("https://changed-origin.example.test/v1")
    page.get_by_role("button", name="Save connection", exact=True).click()
    origin_error = "Remove the stored API key before changing the endpoint origin."
    page.get_by_text(origin_error, exact=True).wait_for(state="visible")
    assert remote_a.locator(".connection-endpoint").inner_text() == "https://api.example.test/v1"
    assert remote_a.get_by_role("button", name="Remove key", exact=True).is_visible()
    evidence_dir = os.getenv("AURA_BROWSER_EVIDENCE_DIR")
    if evidence_dir:
        page.screenshot(
            path=str(
                Path(evidence_dir)
                / "screenshots"
                / "a1g-credentialed-origin-change-rejected.png"
            ),
            full_page=True,
        )

    snapshot = page.evaluate(
        """async () => {
            const token = sessionStorage.getItem('aura_access_token');
            const response = await fetch('/api/settings/models', {
                headers: {Authorization: `Bearer ${token}`}
            });
            return await response.json();
        }"""
    )
    assert synthetic_key not in json.dumps(snapshot)
    storage_dump = page.evaluate(
        "() => JSON.stringify([localStorage, sessionStorage].map(storage => "
        "Object.keys(storage).map(key => [key, storage.getItem(key)])))"
    )
    assert synthetic_key not in storage_dump
    assert any(item["has_api_key"] for item in snapshot["connections"] if item["id"] == remote_a_id)

    remote_b = _add_connection(
        page,
        "Remote Beta",
        "openai_compatible",
        "https://alternate.example.test/v1",
        token_parameter="max_completion_tokens",
    )
    remote_b_id = remote_b.get_attribute("data-connection-id")
    assert remote_b_id and remote_a_id != remote_b_id

    page.locator("#local-only-toggle").uncheck()
    page.wait_for_function("() => document.querySelector('#local-only-state').textContent.includes('Off')")
    assert "may leave this device" in page.locator("#local-only-state").inner_text()
    remote_a.get_by_role("button", name="Test", exact=True).click()
    remote_a.locator(".connection-state").filter(has_text="Authentication failed").wait_for(state="visible")
    _capture(browser_session, "a1g-models-connection-failed.png")
    remote_a.get_by_role("button", name="Remove key", exact=True).click()
    remote_a.get_by_role("button", name="Key not set", exact=True).wait_for(state="visible")
    assert synthetic_key not in page.evaluate(
        "() => JSON.stringify([localStorage, sessionStorage].map(storage => "
        "Object.keys(storage).map(key => [key, storage.getItem(key)])))"
    )

    remote_b.get_by_role("button", name="Test", exact=True).click()
    remote_b.locator(".connection-state").filter(has_text="Connected").wait_for(state="visible")
    remote_b.get_by_role("button", name="Discover models", exact=True).click()
    page.locator("#role-model option[value='gpt-test-2']").wait_for(state="attached")
    _set_model_role(page, "router", remote_b_id, "gpt-test-2", discovered=True)
    assert "Remote Beta · gpt-test-2" in page.locator("#role-summary").inner_text()

    _set_model_role(page, "chat", remote_b_id, "gpt-test", discovered=True)
    page.get_by_role("button", name="Close settings", exact=True).click()
    remote_prompt = "A private prompt for synthetic remote Chat."
    page.locator("#chat-input").fill(remote_prompt)
    _clear_test_rate_limit_state()
    page.get_by_role("button", name="Send message", exact=True).click()
    remote_response = page.locator(".streaming-message").last
    remote_response.locator(".streamed-content").get_by_text("Synthetic stream response.", exact=True).wait_for(state="visible")
    assert remote_response.locator(".message-source").inner_text() == "OpenAI-compatible"
    remote_chat_request = next(
        item for item in reversed(transport.requests)
        if item["url"].endswith("/v1/chat/completions")
    )
    remote_payload = json.loads(remote_chat_request["body"])
    assert [item["role"] for item in remote_payload["messages"]] == ["system", "user"]
    assert remote_payload["messages"][1]["content"] == remote_prompt

    _open_models(page)
    page.locator("#local-only-toggle").check()
    page.wait_for_function("() => document.querySelector('#local-only-state').textContent.includes('On')")
    assert "On" in page.locator("#local-only-state").inner_text()
    blocked_chat_requests = len(transport.requests)
    page.get_by_role("button", name="Close settings", exact=True).click()
    page.locator("#chat-input").fill("Try to send while Local only is on.")
    _clear_test_rate_limit_state()
    page.get_by_role("button", name="Send message", exact=True).click()
    blocked_chat = page.locator(".streaming-message").last
    blocked_chat.locator(".streamed-content").get_by_text("Local only settings blocked this provider request.", exact=True).wait_for(state="visible")
    assert len(transport.requests) == blocked_chat_requests
    _open_models(page)
    _set_model_role(page, "chat", local_id, "qwen2.5:latest", discovered=True)

    # A separate failed local connection demonstrates an actionable unavailable state.
    unavailable = _add_connection(
        page,
        "Unavailable local",
        "ollama",
        "http://127.0.0.1:11434/synthetic-unavailable",
    )
    unavailable.get_by_role("button", name="Test", exact=True).click()
    unavailable.locator(".connection-state").filter(has_text="Unavailable").wait_for(state="visible")

    remote_b.get_by_role("button", name="Remove", exact=True).click()
    page.get_by_text("Remote Beta · gpt-test-2 · Unavailable", exact=False).wait_for(state="visible")
    assert "Studio Ollama · qwen2.5:latest" in page.locator("#role-summary").inner_text()
    _capture(browser_session, "a1g-models-removed-role-unavailable.png")

    # The role persists across a real application reload and still names the exact model.
    page.reload(wait_until="domcontentloaded")
    page.locator("#aura-auth-panel").wait_for(state="hidden")
    _open_models(page)
    assert "Studio Ollama · qwen2.5:latest" in page.locator("#role-summary").inner_text()
    page.get_by_role("button", name="Close settings", exact=True).click()

    # Models Settings remain usable without horizontal overflow at every target width.
    for width, height, capture_name in (
        (1440, 900, None),
        (390, 844, "a1g-models-mobile-390x844.png"),
        (320, 844, "a1g-models-mobile-320x844.png"),
        (768, 1024, "a1g-models-tablet-768x1024.png"),
        (1024, 768, "a1g-models-tablet-1024x768.png"),
    ):
        page.set_viewport_size({"width": width, "height": height})
        _wait_for_layout_transition(page, width)
        _open_models(page)
        assert page.evaluate("() => document.documentElement.scrollWidth") <= width + 1
        if width <= 768:
            targets = page.locator("#models-panel button:visible").evaluate_all(
                "elements => elements.map(element => { const r = element.getBoundingClientRect(); "
                "return {name: element.innerText, width: r.width, height: r.height}; })"
            )
            assert all(item["width"] >= 44 and item["height"] >= 44 for item in targets), targets
        if capture_name:
            _capture(browser_session, capture_name)
        page.get_by_role("button", name="Close settings", exact=True).click()

    _open_models(page)
    model_contrast_failures = _contrast_failures(page, "#models-panel")
    assert not model_contrast_failures, f"Models text contrast below 4.5:1: {model_contrast_failures}"
    page.get_by_role("button", name="Close settings", exact=True).click()

    page.set_viewport_size({"width": 1440, "height": 900})
    page.get_by_role("button", name="Chat", exact=True).click()

    # Release one controlled frame only after the browser has rendered it, proving progressive UI.
    transport.next_stream_behavior = "progressive"
    page.locator("#chat-input").fill("Could you give me a short example?")
    _clear_test_rate_limit_state()
    first_token_started = time.perf_counter()
    page.get_by_role("button", name="Send message", exact=True).click()
    progressive = page.locator(".streaming-message").last
    progressive.locator(".streamed-content").get_by_text("Synthetic", exact=False).wait_for(state="visible")
    measurements["first_synthetic_token_ms"] = round((time.perf_counter() - first_token_started) * 1000, 2)
    assert page.get_by_role("button", name="Stop", exact=True).is_visible()
    assert page.get_by_role("button", name="Send message", exact=True).is_hidden()
    assert progressive.locator(".message-source").inner_text() == "Local"
    _capture(browser_session, "a1g-chat-active-streaming.png")
    transport.release_slow_stream.set()
    page.wait_for_function(
        "() => document.querySelector('.streaming-message:last-of-type .streamed-content')"
        "?.textContent === 'Synthetic stream response.'"
    )
    page.get_by_text("Response complete", exact=True).wait_for(state="visible")

    before_stop_count = _assistant_history_count(browser_session)
    transport.next_stream_behavior = "slow"
    page.locator("#chat-input").fill("Please start an answer and wait.")
    _clear_test_rate_limit_state()
    page.get_by_role("button", name="Send message", exact=True).click()
    stopped = page.locator(".streaming-message").last
    stopped.locator(".streamed-content").get_by_text("Synthetic partial", exact=False).wait_for(state="visible")
    stop_button = page.get_by_role("button", name="Stop", exact=True)
    cancellation_started = time.perf_counter()
    stop_button.focus()
    page.keyboard.press("Enter")
    stopped.locator(".message-completion-status").get_by_text("Stopped", exact=True).wait_for(state="visible")
    stopped = page.locator(".streaming-message.stopped").last
    assert transport.streams_closed_event.wait(timeout=5), "Cancelled upstream response was not closed."
    measurements["stream_cancellation_cleanup_ms"] = round(
        (time.perf_counter() - cancellation_started) * 1000, 2
    )
    assert _assistant_history_count(browser_session) == before_stop_count
    stopped_text = stopped.locator(".streamed-content").inner_text()
    assert stopped_text == "Synthetic partial"
    _capture(browser_session, "a1g-chat-stopped.png")

    # Another request is accepted after cancellation, with no stale stream append.
    page.locator("#chat-input").fill("Can you answer after cancellation?")
    _clear_test_rate_limit_state()
    page.get_by_role("button", name="Send message", exact=True).click()
    subsequent = page.locator(".streaming-message").last
    subsequent.locator(".streamed-content").get_by_text("Synthetic stream response.", exact=True).wait_for(state="visible")
    page.get_by_text("Response complete", exact=True).wait_for(state="visible")
    assert stopped.locator(".streamed-content").inner_text() == stopped_text

    # Leaving Chat aborts the same active controller and does not commit the partial answer.
    before_navigation_count = _assistant_history_count(browser_session)
    transport.next_stream_behavior = "navigation"
    navigation_bubble_index = page.locator(".streaming-message").count()
    page.locator("#chat-input").fill("Stop this answer by navigating away.")
    _clear_test_rate_limit_state()
    page.get_by_role("button", name="Send message", exact=True).click()
    navigation_stopped = page.locator(".streaming-message").nth(navigation_bubble_index)
    navigation_stopped.locator(".streamed-content").get_by_text(
        "Synthetic partial", exact=False
    ).wait_for(state="visible")
    page.get_by_role("button", name="Tasks", exact=True).click()
    _assert_active_view(page, "tasks")
    assert transport.streams_closed_event.wait(timeout=5), (
        "Navigating away did not close the upstream provider stream."
    )
    page.get_by_role("button", name="Chat", exact=True).click()
    navigation_stopped.locator(".message-completion-status").get_by_text(
        "Stopped", exact=True
    ).wait_for(state="visible")
    navigation_text = navigation_stopped.locator(".streamed-content").inner_text()
    assert navigation_text == "Synthetic partial"
    assert _assistant_history_count(browser_session) == before_navigation_count
    page.wait_for_function(
        "() => Number.parseFloat(getComputedStyle(document.querySelector('#view-chat')).opacity) >= 0.99"
    )
    _capture(browser_session, "a1g-chat-stopped-on-navigation.png")

    # Ordinary navigation with no active stream remains usable, and a new request can run.
    page.get_by_role("button", name="Tasks", exact=True).click()
    _assert_active_view(page, "tasks")
    page.get_by_role("button", name="Chat", exact=True).click()
    _assert_active_view(page, "chat")
    assert navigation_stopped.locator(".streamed-content").inner_text() == navigation_text
    page.locator("#chat-input").fill("Can Chat run after navigation cancellation?")
    _clear_test_rate_limit_state()
    page.get_by_role("button", name="Send message", exact=True).click()
    after_navigation = page.locator(".streaming-message").last
    after_navigation.locator(".streamed-content").get_by_text(
        "Synthetic stream response.", exact=True
    ).wait_for(state="visible")
    assert navigation_stopped.locator(".streamed-content").inner_text() == navigation_text

    # Unavailable, missing-model and interrupted outputs remain visibly unsuccessful.
    _open_models(page)
    unavailable_id = unavailable.get_attribute("data-connection-id")
    assert unavailable_id
    _set_model_role(page, "chat", unavailable_id, "qwen2.5:latest", discovered=False)
    page.get_by_role("button", name="Close settings", exact=True).click()

    page.locator("#chat-input").fill("Can you help me with this?")
    _clear_test_rate_limit_state()
    page.get_by_role("button", name="Send message", exact=True).click()
    failed = page.locator(".streaming-message").last
    failed.locator(".streamed-content").get_by_text("Provider is unavailable.", exact=True).wait_for(state="visible")
    assert "error" in (failed.get_attribute("class") or "")
    _capture(browser_session, "a1g-chat-provider-error.png")

    _open_models(page)
    _set_model_role(page, "chat", local_id, "SYNTHETIC_MODEL_MISSING", discovered=False)
    page.get_by_role("button", name="Close settings", exact=True).click()
    page.locator("#chat-input").fill("Check the selected model.")
    _clear_test_rate_limit_state()
    page.get_by_role("button", name="Send message", exact=True).click()
    missing = page.locator(".streaming-message").last
    missing.locator(".streamed-content").get_by_text("The selected model is unavailable.", exact=True).wait_for(state="visible")

    _open_models(page)
    page.locator(".connection-row").filter(has_text="Studio Ollama").get_by_role(
        "button", name="Discover models", exact=True
    ).click()
    page.locator("#role-model option[value='qwen2.5:latest']").wait_for(state="attached")
    _set_model_role(page, "chat", local_id, "qwen2.5:latest", discovered=True)
    page.get_by_role("button", name="Close settings", exact=True).click()
    transport.next_stream_behavior = "interrupted"
    page.locator("#chat-input").fill("Please finish this response.")
    _clear_test_rate_limit_state()
    page.get_by_role("button", name="Send message", exact=True).click()
    interrupted = page.locator(".streaming-message").last
    interrupted.locator(".streamed-content").get_by_text("partial", exact=True).wait_for(state="visible")
    interrupted.locator(".message-completion-status").get_by_text("Incomplete response", exact=True).wait_for(state="visible")

    # Reduced motion is checked in the real browser and captured for review.
    page.emulate_media(reduced_motion="reduce")
    _open_models(page)
    motion = page.evaluate(
        """() => [...document.querySelectorAll('*')].map(element => {
            const style = getComputedStyle(element);
            const parse = value => value.split(',').map(item => {
                const text = item.trim();
                if (text.endsWith('ms')) return Number.parseFloat(text);
                if (text.endsWith('s')) return Number.parseFloat(text) * 1000;
                return 0;
            });
            return Math.max(...parse(style.animationDuration), ...parse(style.transitionDuration));
        }).reduce((max, value) => Math.max(max, value), 0)"""
    )
    assert motion <= 120, f"Reduced motion duration exceeded 120 ms: {motion}"
    _capture(browser_session, "a1g-reduced-motion-models.png")
    page.get_by_role("button", name="Close settings", exact=True).click()
    page.get_by_role("button", name="Chat", exact=True).click()
    _assert_active_view(page, "chat")
    _capture(browser_session, "a1g-reduced-motion-chat.png")

    # No provider key is stored in the database as plaintext or sent to the browser storage APIs.
    with browser_session.application.session_factory() as db:
        rows = db.query(ChatHistory).all()
        assert all(row.user_id is not None for row in rows)
    database_path = browser_session.application.session_factory.kw["bind"].url.database
    assert synthetic_key.encode() not in Path(database_path).read_bytes()
    assert not browser_session.external_attempts
    assert not browser_session.unauthenticated_data_requests
    _assert_no_uncaught_errors(browser_session)
    expected_origin_rejection = [
        error for error in browser_session.console_errors if "409 (Conflict)" in error
    ]
    unexpected_console_errors = [
        error for error in browser_session.console_errors if error not in expected_origin_rejection
    ]
    assert len(expected_origin_rejection) == 1, browser_session.console_errors
    assert not unexpected_console_errors, (
        "Unexpected browser console errors: " + " | ".join(unexpected_console_errors)
    )
    # Chat also remains horizontally contained at all required viewport widths.
    responsive_chat_layout: list[dict[str, object]] = []
    for width, height in _VIEWPORTS:
        page.set_viewport_size({"width": width, "height": height})
        _wait_for_layout_transition(page, width)
        _assert_active_view(page, "chat")
        page.wait_for_function(
            "Number.parseFloat(getComputedStyle(document.querySelector('#view-chat')).opacity) >= 0.99"
        )
        page.locator("#chat-history").evaluate(
            "element => { element.scrollTop = element.scrollHeight; }"
        )
        assert page.locator(".input-area").is_visible(), (
            f"Chat composer is not visible at {width}x{height}"
        )
        geometry = page.evaluate(
            "() => { const bounds = selector => { const element = document.querySelector(selector); "
            "const r = element.getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom, "
            "width:r.width,height:r.height, "
            "cssWidth:getComputedStyle(element).width, inlineWidth:element.style.width}; }; return {width: innerWidth, "
            "clientWidth: document.documentElement.clientWidth, visualWidth: visualViewport.width, "
            "documentWidth: document.documentElement.scrollWidth, app: bounds('.app-container'), "
            "main: bounds('.main-content'), chat: bounds('.chat-container'), "
                "chatView: (() => { const e = document.querySelector('#view-chat'); const s = getComputedStyle(e); "
                "return {display:s.display,visibility:s.visibility,opacity:s.opacity}; })(), "
                "latestMessage: (() => { const items = document.querySelectorAll('#chat-history .message'); "
                "if (!items.length) return null; const e = items[items.length - 1]; const r = e.getBoundingClientRect(); "
                "const s = getComputedStyle(e); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom, "
                "width:r.width,height:r.height,visibility:s.visibility,opacity:s.opacity}; })(), "
                "composer: bounds('.input-area')}; }"
        )
        responsive_chat_layout.append(geometry)
        if width == 1024:
            page.screenshot(
                path=str(
                    Path(os.getenv("AURA_BROWSER_EVIDENCE_DIR"))
                    / "screenshots"
                    / f"a1g-chat-tablet-{width}x{height}.png"
                )
            )
        assert geometry["documentWidth"] <= width + 1, geometry
        assert geometry["composer"]["left"] >= -1 and geometry["composer"]["right"] <= width + 1, geometry
        assert geometry["composer"]["top"] >= -1 and geometry["composer"]["bottom"] <= height + 1, geometry
        assert geometry["latestMessage"] is not None, geometry
        assert geometry["latestMessage"]["bottom"] <= geometry["composer"]["top"], (
            f"Latest Chat message is obscured by the composer at {width}x{height}: {geometry}"
        )
    measurements["chat_responsive_layout"] = responsive_chat_layout
    chat_contrast_failures = _contrast_failures(page, "#view-chat")
    assert not chat_contrast_failures, f"Chat text contrast below 4.5:1: {chat_contrast_failures}"
    evidence_dir = os.getenv("AURA_BROWSER_EVIDENCE_DIR")
    if evidence_dir:
        measurement_path = Path(evidence_dir) / "a1g-browser-measurements.json"
        measurement_path.write_text(json.dumps(measurements, indent=2), encoding="utf-8")


def test_recorded_user_journey(
    browser_session: BrowserSession, browser_account: BrowserCredentials
) -> None:
    """Settings-to-Chat workflow; optionally recorded when AURA_CAPTURE_VIDEO=1."""
    _sign_in(browser_session, browser_account)
    page = browser_session.page
    _open_models(page)
    connection = _add_connection(page, "Recorded Ollama", "ollama", "http://127.0.0.1:11434")
    connection_id = connection.get_attribute("data-connection-id")
    connection.get_by_role("button", name="Test", exact=True).click()
    connection.locator(".connection-state").filter(has_text="Connected").wait_for(state="visible")
    connection.get_by_role("button", name="Discover models", exact=True).click()
    page.locator("#role-connection").select_option(connection_id)
    page.locator("#role-model").select_option("qwen2.5:latest")
    page.get_by_role("button", name="Save role", exact=True).click()
    page.get_by_role("button", name="Close settings", exact=True).click()
    page.get_by_role("button", name="Chat", exact=True).click()
    browser_session.application.provider_transport.next_stream_behavior = "slow"
    page.locator("#chat-input").fill("Please start a short answer.")
    _clear_test_rate_limit_state()
    page.get_by_role("button", name="Send message", exact=True).click()
    page.locator(".streaming-message .streamed-content").get_by_text("Synthetic partial", exact=False).wait_for(state="visible")
    page.get_by_role("button", name="Stop", exact=True).click()
    page.locator(".streaming-message .message-completion-status").get_by_text("Stopped", exact=True).wait_for(state="visible")
    assert browser_session.application.provider_transport.streams_closed_event.wait(timeout=5)
    _assert_no_uncaught_errors(browser_session)


def test_chat_sse_buffers_coalesced_frames_and_bounds_single_frames(
    browser_session: BrowserSession, browser_account: BrowserCredentials
) -> None:
    """Accept coalesced valid frames while bounding complete and incomplete frames."""
    _sign_in(browser_session, browser_account)
    page = browser_session.page
    _assert_active_view(page, "chat")

    page.evaluate(
        """() => {
            window.__auraSsePayload = '';
            window.__auraSseChunks = null;
            window.apiFetch = async function(url, options = {}) {
                if (!String(url).endsWith('/chat/stream')) return fetch(url, options);
                const chunks = window.__auraSseChunks
                    || [new TextEncoder().encode(window.__auraSsePayload)];
                const body = new ReadableStream({
                    start(controller) {
                        for (const chunk of chunks) controller.enqueue(new Uint8Array(chunk));
                        controller.close();
                    }
                });
                return new Response(body, {
                    status: 200,
                    headers: {'content-type': 'text/event-stream'}
                });
            };
        }"""
    )

    def frame(event_name: str, payload: dict[str, object]) -> str:
        return f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"

    request_id = "synthetic-coalesced-frame-test"
    payload = frame(
        "started",
        {"request_id": request_id, "model_id": "synthetic-model", "provider_type": "ollama", "locality": "local"},
    )
    expected = "x" * 900 * 40
    payload += "".join(
        frame("text_delta", {"request_id": request_id, "delta": "x" * 900})
        for _ in range(40)
    )
    payload += frame("completed", {"request_id": request_id})
    assert len(payload.encode("utf-8")) > 32_768
    page.evaluate(
        "payload => { window.__auraSsePayload = payload; window.__auraSseChunks = null; }",
        payload,
    )
    page.locator("#chat-input").fill("Read coalesced synthetic frames")
    page.get_by_role("button", name="Send message", exact=True).click()
    complete = page.locator(".streaming-message").last
    page.wait_for_function(
        "() => ['Response complete', 'Response unavailable', 'Response interrupted'].includes("
        "document.querySelector('#chat-status')?.textContent)"
    )
    assert complete.locator(".streamed-content").inner_text() == expected
    assert "error" not in (complete.get_attribute("class") or "")

    fragment_id = "synthetic-fragmented-utf8-test"
    fragment_text = "A🙂é"
    fragmented = frame(
        "started",
        {"request_id": fragment_id, "model_id": "synthetic-model", "provider_type": "ollama", "locality": "local"},
    )
    fragmented += (
        "event: text_delta\ndata: "
        + json.dumps(
            {"request_id": fragment_id, "delta": fragment_text},
            ensure_ascii=False,
        )
        + "\n\n"
    )
    fragmented += frame("completed", {"request_id": fragment_id})
    encoded = fragmented.encode("utf-8")
    emoji_offset = encoded.index("🙂".encode("utf-8"))
    delimiter_offset = encoded.index(b"\n\n", emoji_offset)
    chunks = [
        list(encoded[: emoji_offset + 2]),
        list(encoded[emoji_offset + 2 : delimiter_offset + 1]),
        list(encoded[delimiter_offset + 1 :]),
    ]
    page.evaluate("chunks => { window.__auraSseChunks = chunks; }", chunks)
    page.locator("#chat-input").fill("Read fragmented UTF-8 frames")
    page.get_by_role("button", name="Send message", exact=True).click()
    fragmented_bubble = page.locator(".streaming-message").last
    page.wait_for_function(
        "() => document.querySelector('#chat-status')?.textContent === 'Response complete'"
    )
    assert fragmented_bubble.locator(".streamed-content").inner_text() == fragment_text

    oversized_id = "synthetic-oversized-complete-frame"
    oversized_complete = frame(
        "started",
        {"request_id": oversized_id, "model_id": "synthetic-model", "provider_type": "ollama", "locality": "local"},
    ) + frame(
        "text_delta",
        {"request_id": oversized_id, "delta": "s" * 33_000},
    )
    page.evaluate(
        "payload => { window.__auraSsePayload = payload; window.__auraSseChunks = null; }",
        oversized_complete,
    )
    page.locator("#chat-input").fill("Reject an oversized complete frame")
    page.get_by_role("button", name="Send message", exact=True).click()
    rejected_complete = page.locator(".streaming-message").last
    rejected_complete.locator(".streamed-content").get_by_text(
        "The Chat stream exceeded its event limit.", exact=True
    ).wait_for(state="visible")
    assert "error" in (rejected_complete.get_attribute("class") or "")
    assert "s" * 500 not in rejected_complete.locator(".streamed-content").inner_text()

    oversized_incomplete = frame(
        "started",
        {"request_id": "synthetic-oversized-incomplete-frame", "model_id": "synthetic-model", "provider_type": "ollama", "locality": "local"},
    ) + 'event: text_delta\ndata: {"request_id":"synthetic-oversized-incomplete-frame","delta":"' + "u" * 33_000
    page.evaluate(
        "payload => { window.__auraSsePayload = payload; window.__auraSseChunks = null; }",
        oversized_incomplete,
    )
    page.locator("#chat-input").fill("Reject an oversized incomplete frame")
    page.get_by_role("button", name="Send message", exact=True).click()
    rejected_incomplete = page.locator(".streaming-message").last
    rejected_incomplete.locator(".streamed-content").get_by_text(
        "The Chat stream exceeded its event limit.", exact=True
    ).wait_for(state="visible")
    assert "error" in (rejected_incomplete.get_attribute("class") or "")
    assert "u" * 500 not in rejected_incomplete.locator(".streamed-content").inner_text()
    assert not browser_session.external_attempts
    _assert_no_uncaught_errors(browser_session)
