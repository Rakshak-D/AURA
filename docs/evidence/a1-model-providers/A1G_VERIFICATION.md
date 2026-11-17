# A1-G Verification Record

Date: 2026-11-17

Branch: `feat/a1-model-providers`

Starting review base: `bfd1723f88a7e4ffc9ca78f52b14650061e9d4ea`

Verified UI/test source commit: `d16cdcf` (`Add functional model settings and streaming chat UI`)

## Scope delivered

The authenticated Models settings screen manages named Ollama and OpenAI-compatible connections, write-only credentials, connection/model testing and discovery, per-role connection/model selection, capability provenance, and the server-enforced Local only switch. Removed connections remain visible when a saved role references them. No role or model is assigned automatically.

Chat uses the selected backend model through authenticated `POST /api/chat/stream` Server-Sent Events. Text appears progressively, the source label comes from the server response, and Stop cancels the request. Only complete answers are stored as assistant history. The existing authenticated settings endpoints are under `/api/settings/models`; they cover connection CRUD, credentials, discovery/testing, capability reads, role selection, and Local only.

The browser UI does not receive provider credentials. Credential sentinels were checked against the temporary database bytes, settings responses, and browser storage. Existing ownership checks, provider error normalization, A1-D transport policy, and action boundaries were exercised by the backend regressions and left intact.

## Verification results

Local AURA app, browser, authentication, and SQLite interactions ran on Windows. Provider behavior and provider responses were synthetic; no real provider or network service was contacted.

| Check | Command / environment | Result |
| --- | --- | --- |
| Backend suite, Python 3.11.7 | `$env:PYTHONPATH='.'; & 'C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\py311\Scripts\python.exe' -m pytest -m 'not browser' -q -rs --tb=short` | **PASS_REAL** — 353 passed, 8 deselected, 3 warnings, 113.56 s |
| Backend suite, Python 3.12.10 | `$env:PYTHONPATH='.'; & 'C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\py312\Scripts\python.exe' -m pytest -m 'not browser' -q -rs --tb=short` | **PASS_REAL** — 353 passed, 8 deselected, 4 warnings, 113.21 s |
| Browser suite, Python 3.11.7 | `$env:PYTHONPATH='.'; $env:AURA_RUN_BROWSER='1'; $env:AURA_CAPTURE_VIDEO='1'; $env:AURA_BROWSER_EVIDENCE_DIR='docs/evidence/a1-model-providers'; & 'C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\py311\Scripts\python.exe' -m pytest -m browser -q -rs --tb=short` | **PASS_REAL / PASS_SYNTHETIC** — 8 passed, 353 deselected, 3 warnings, 94.60 s |
| Focused A1-G browser journey | `$env:PYTHONPATH='.'; $env:AURA_RUN_BROWSER='1'; $env:AURA_CAPTURE_VIDEO='1'; $env:AURA_BROWSER_EVIDENCE_DIR='docs/evidence/a1-model-providers'; & 'C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\py311\Scripts\python.exe' -m pytest tests/browser/test_frontend_smoke.py::test_a1g_models_and_streaming_regressions -q -rs --tb=short` | **PASS_REAL / PASS_SYNTHETIC** — 1 passed, 3 warnings, 38.89 s |
| Compile, Python 3.11 and 3.12 | `python -m compileall -q backend tests scripts` with task-local `PYTHONPYCACHEPREFIX` | **PASS_REAL** — both exited 0 |
| Ruff, Python 3.11 and 3.12 | `python -m ruff check backend tests scripts --select E4,E7,E9,F --no-cache` | **PASS_REAL** — `All checks passed!` on both |
| Dependency consistency, Python 3.11 and 3.12 | `python -m pip check` | **PASS_REAL** — `No broken requirements found.` on both |
| Frontend JavaScript syntax | `node --check frontend/js/chat.js`; `node --check frontend/js/main.js`; `node --check frontend/js/settings.js` | **PASS_REAL** — all exited 0 |
| Frontend API contract | `node tests/frontend_contracts.test.mjs` | **PASS_REAL** — `frontend API contract checks passed` |
| Patch whitespace | `git diff --check` | **PASS_REAL** — exit 0; Git emitted only its LF-to-CRLF advisory for the browser test file |

The backend warnings are existing Pydantic v2 class-config deprecations; Python 3.12 also reports the existing `tarfile.extractall` deprecation warning in the backup test. No test failed or skipped beyond the 8 browser-marked tests in the backend-only runs.

## Browser and responsive evidence

The complete browser run recorded 8 test entries. It observed zero external request attempts, zero unauthenticated data requests, and zero uncaught JavaScript errors. The A1-G journey itself recorded no console errors. The separate missing-local-icon test deliberately blocks the Lucide resource and records two expected `ERR_BLOCKED_BY_CLIENT` console messages.

The A1-G browser regression checks responsive Chat at 1440×900, 1024×768, 768×1024, 390×844, and 320×844. It scrolls to the latest message after resizing and checks the latest message clears the composer. The smallest measured gap was over 75 px; the composer and document remained within the viewport at all five sizes. The Models UI was captured at desktop, tablet, and 390×844 / 320×844 mobile sizes. Visible Models controls met the 44 px minimum, and the reduced-motion check measured no transition/animation over 120 ms.

Synthetic timing measurements from the browser harness: app startup 533.01 ms with no model initialization; initial Models render 256.88 ms; local connection test 236.26 ms; synthetic model listing 174.15 ms; first synthetic token 62.68 ms; cancellation cleanup 19.97 ms. These are local test measurements, not provider latency claims.

Current checked-in static payload totals measured from Chromium CDP: 914,269 body bytes and 301,874 encoded transfer bytes. Comparing the five changed initial HTML/CSS/JS resources with the review base adds 55,089 source bytes before transfer compression. Vendor assets were unchanged.

Screenshots, a contact sheet, responsive measurements, browser request/error summary, payload measurements, and the synthetic Settings-to-Chat recording are stored under this evidence directory. The recording and screenshots demonstrate synthetic provider states only.

## Dependencies, platform, and limitations

No production dependency or dependency manifest changed. Playwright 1.65.2 was installed only in the task's temporary Python 3.11 environment for browser execution. Python 3.11 and 3.12 were exercised on Windows. Linux execution and hosted CI were **NOT_TESTED**.

No Ollama process was started, no cloud provider was contacted, no real credential was used, and no model was downloaded or executed. Actual Ollama/OpenAI-compatible server compatibility and remote latency remain unverified. The application was not pushed; hosted CI remains **NOT_TESTED**.

## Repository hygiene

Stage C introduced no source directories. Browser evidence uses the existing `docs/evidence/a1-model-providers/` location; its `screenshots/` and `recordings/` subdirectories hold the required review artifacts. Temporary browser-only diagnostic screenshots were removed after inspection. The task-generated Python compile cache was kept outside the repository. Existing ignored caches and historical A0 console evidence were left untouched because their ownership predates this stage or is uncertain.

The pre-existing untracked `docs/evidence/a1-model-providers.zip` was preserved unchanged and unstaged (SHA-256 `83E5DA7E602CC8DD2CFA090D46A3828FFB9F44163478B60726BA605B28AB115F`). No secrets, databases, model weights, or private data were added. No push, PR, merge, or deployment was performed. A1-H and later work has not started.
