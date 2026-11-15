# A0 Baseline Evidence

Captured 2026-11-15 against the unmodified A0 starting commit.

## Repository preflight

- Starting branch: `main`.
- Local `HEAD`, fetched `origin/main`, and `FETCH_HEAD`: `b3e46b8f3f24b67919a396d4b93517fd5dec46b8`.
- Starting worktree: clean.
- Local and remote `feat/a0-foundation` branches: absent before work.
- The requested feature branch was created from this commit.
- Repository: `https://github.com/Rakshak-D/AURA.git`.

## Architecture checks

The inspected sources match the supplied baseline: FastAPI, SQLAlchemy and SQLite, APScheduler, a vanilla HTML/CSS/JavaScript frontend, optional in-process GGUF inference, nine strict discriminated Pydantic actions, authenticated ownership checks, destructive-action confirmation, reminder retry handling, and one-time WebSocket tickets. Core pins include FastAPI 0.104.1 and Pydantic 2.5.0. The known Lucide, Chart.js, and Google Fonts references are present in the browser code. Recents, Saved, and Projects are visible but have no navigation handlers.

## Backend test baseline

**Status:** `PASS_SYNTHETIC` — the real repository tests ran on Windows Python 3.11.7 with isolated temporary SQLite data; the suite uses its existing test fixtures and doubles for optional runtimes.

- Python: 3.11.7, 64-bit Windows (`Windows-10-10.0.26300-SP0`).
- Core versions: FastAPI 0.104.1, Uvicorn 0.24.0, Pydantic 2.5.0, pydantic-settings 2.1.0, SQLAlchemy 2.0.23, APScheduler 3.10.4, SlowAPI 0.1.9, PyJWT 2.8.0, pwdlib 0.2.0.
- Test versions: pytest 7.4.3, pytest-asyncio 0.21.1, httpx 0.25.2, pytest-cov 4.1.0.
- Collection: 97 tests, including the opt-in browser test.
- Deterministic suite: 96 passed, 1 deselected (`browser` marker), 0 failed, 0 skipped, 0 errors; 8 warnings.
- Ruff was omitted from this baseline-only temporary environment because its 9.4 MB wheel was still downloading at very low throughput. Ruff is declared as 0.6.9 in `requirements-dev.txt`; no lint claim is made for baseline.

Commands (run with the isolated Python 3.11.7 environment created from the existing manifest):

```powershell
<baseline-venv>\Scripts\python.exe -m pytest --collect-only -q
<baseline-venv>\Scripts\python.exe -m pytest -m "not browser" -q
```

## Real browser baseline

**Status:** `PASS_REAL` for sign-in, Tasks, Chat, and Insights with the local FastAPI app, its disposable SQLite database, and public CDNs reachable. Chrome 157.0.0.0 was controlled with Playwright CLI 0.1.23. The optional model runtime was absent. Chat submitted through the real UI/backend path and displayed the backend fallback `I'm having trouble thinking right now.`; no real-model answer was run.

**Status:** `FAIL` for offline startup. A browser route blocked all non-local hosts and reloaded the page. The Lucide script failed to load; both the trailing icon initializer and the `DOMContentLoaded` initializer raised `ReferenceError: lucide is not defined`. The sign-in panel was never created. Screenshot: `cdn-blocked-signin-1440x900.png`; request and console logs: `blocked-external-requests.txt` and `blocked-browser-console.txt`.

Normal-network browser evidence:

- `signin-1440x900.png`, `signin-1024x768.png`, `signin-390x844.png`.
- `chat-1440x900.png`, `chat-fallback-1440x900.png`, `tasks-1440x900.png`, `insights-1440x900.png`.
- Sign-in created and authenticated a disposable local test account. Tasks rendered from the authenticated API. Chat returned a graceful no-model fallback. Insights created two real Chart.js canvases (runtime version 4.6.1). Lucide initialized 23 page icons.
- Initial browser console: 7 errors, 0 warnings. The errors were the Google Fonts CSP block, three expected unauthenticated API 401s plus task/upload error logs before sign-in, and a missing favicon 404.
- External URL attempts: 4 records across three hostnames—Lucide `@latest` plus its `1.73.0` redirect target, Chart.js from jsDelivr, and Google Fonts (blocked by the existing CSP). The normal-network details are in `external-requests.txt`; the browser guard capture is in `blocked-external-requests.txt`.

## Initial static payload

Measured in the browser with Chromium DevTools Protocol `Network.loadingFinished.encodedDataLength`, with browser cache disabled. API responses are excluded from these static-asset totals. The Google Fonts request was blocked by CSP and transferred 0 bytes.

| Resource | Uncompressed body bytes | Observed transfer bytes |
|---|---:|---:|
| Initial HTML | 14,952 | 15,644 |
| CSS | 28,745 | 29,436 |
| Directly loaded local JavaScript (10 files) | 71,483 | 78,375 |
| Chart.js CDN script (4.6.1) | 210,082 | 62,151 |
| Lucide CDN script (1.73.0, redirected from `@latest`) | 487,171 | 114,950 |
| **Initial static payload total** | **802,433** | **300,556** |

The local JavaScript transfer subtotal includes each response's headers; the decoded body subtotal is exact from the local file sizes. Two existing scripts, `keyboard.js` and `search.js`, were not referenced by the initial HTML and are excluded from the page total. No local font files existed at baseline.
