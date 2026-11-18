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

## A1-G-R1 corrective verification — 2026-11-17

This append-only addendum records R1 verification after the original A1-G evidence above. Earlier measurements and screenshots remain historical and were not rewritten. Browser-generated outputs from the R1 rerun were restored unless they show the two new R1 states below.

### Corrections

- Connection creation and URL updates reuse A1-D's side-effect-free endpoint parser before persistence. Embedded URL credentials, secret-bearing query keys, fragments, unsupported schemes, malformed ports, and malformed hosts are rejected with a static actionable message. Saving configuration performs no DNS resolution or provider request.
- A credentialed connection retains its key when its normalized scheme, host, and port stay the same, including API path edits. Changes to scheme, host, or port are rejected until the owner removes the key. The key remains write-only and encrypted at rest.
- SSE parsing extracts complete frames before applying the 32 KiB per-frame limit. Incomplete residuals remain bounded, displayed UTF-8 response content stays capped at 1 MiB, and tests cover fragmented UTF-8 plus a delimiter split across network chunks.
- Leaving the active Chat view aborts the existing request controller. The synthetic upstream stream closes; the partial answer is not written to completed assistant history; the stopped bubble remains unchanged; and another Chat request succeeds.
- New browser captures: screenshots/a1g-credentialed-origin-change-rejected.png and screenshots/a1g-chat-stopped-on-navigation.png.

### Verification results

All executions ran on this Windows host. Browser interactions used the local AURA app and disposable SQLite fixtures; provider responses and the synthetic SSE stream were controlled test data. No real Ollama/cloud request, model download, or credential was used.

For the PowerShell commands below, $py311 was C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\py311\Scripts\python.exe and $py312 was C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\py312\Scripts\python.exe.

- Model Settings API regressions, Python 3.11.7: command $env:PYTHONPATH='.'; $env:PYTHONDONTWRITEBYTECODE='1'; & $py311 -m pytest -p no:cacheprovider tests/test_model_settings.py -q -rs --tb=short — PASS_REAL, 20 passed, 3 existing Pydantic deprecation warnings, 7.59 s.
- Provider, credential, transport, Chat, and web-security group, Python 3.11.7: command $env:PYTHONPATH='.'; $env:PYTHONDONTWRITEBYTECODE='1'; & $py311 -m pytest -p no:cacheprovider tests/test_model_settings.py tests/test_web_security.py tests/test_chat_streaming.py tests/test_provider_adapters.py tests/test_provider_contracts.py tests/test_provider_network_policy.py tests/test_provider_secrets.py tests/test_provider_storage.py -q -rs --tb=short — PASS_REAL / PASS_SYNTHETIC, 279 passed, 3 existing Pydantic warnings, 54.12 s.
- Full non-browser backend, Python 3.11.7: command $env:PYTHONPATH='.'; $env:PYTHONDONTWRITEBYTECODE='1'; & $py311 -m pytest -p no:cacheprovider -m 'not browser' -q -rs --tb=short — PASS_REAL / PASS_SYNTHETIC, 368 passed, 9 browser tests deselected, 3 existing Pydantic warnings, 69.64 s.
- Full non-browser backend, Python 3.12.10: command $env:PYTHONPATH='.'; $env:PYTHONDONTWRITEBYTECODE='1'; & $py312 -m pytest -p no:cacheprovider -m 'not browser' -q -rs --tb=short — PASS_REAL / PASS_SYNTHETIC, 368 passed, 9 browser tests deselected, 4 warnings (3 existing Pydantic and the existing tarfile.extractall deprecation), 69.42 s.
- Coalesced and fragmented SSE plus size-limit browser regression, Python 3.11.7: command $env:PYTHONPATH='.'; $env:AURA_RUN_BROWSER='1'; & $py311 -m pytest tests/browser/test_frontend_smoke.py::test_chat_sse_buffers_coalesced_frames_and_bounds_single_frames -q -rs --tb=short — PASS_REAL / PASS_SYNTHETIC, 1 passed, 3 existing Pydantic warnings, 6.04 s.
- A1-G Settings and navigation regression, Python 3.11.7: command $env:PYTHONPATH='.'; $env:AURA_RUN_BROWSER='1'; $env:AURA_BROWSER_EVIDENCE_DIR='docs/evidence/a1-model-providers'; & $py311 -m pytest -p no:cacheprovider tests/browser/test_frontend_smoke.py::test_a1g_models_and_streaming_regressions -q -rs --tb=short — PASS_REAL / PASS_SYNTHETIC, 1 passed, 3 existing Pydantic warnings, 41.38 s.
- Full Playwright suite, Python 3.11.7: command $env:PYTHONPATH='.'; $env:PYTHONDONTWRITEBYTECODE='1'; $env:AURA_RUN_BROWSER='1'; $env:AURA_BROWSER_EVIDENCE_DIR=$evidenceRoot (unique system-temp directory, removed after verification); & $py311 -m pytest -p no:cacheprovider -m browser -q -rs --tb=short — PASS_REAL / PASS_SYNTHETIC, 9 passed, 368 backend tests deselected, 3 existing Pydantic warnings, 99.01 s.
- Python compile: python -m compileall -q backend tests scripts ran on Python 3.11.7 and 3.12.10 with a task-specific system-temp PYTHONPYCACHEPREFIX — PASS_REAL, both exited 0; the task-owned cache was removed after its path was verified.
- Ruff: python -m ruff check backend tests scripts --select E4,E7,E9,F --no-cache — PASS_REAL, All checks passed! on Python 3.11.7 and 3.12.10.
- Dependency checks: python -m pip check — PASS_REAL, No broken requirements found. on both Python versions.
- Frontend checks: node --check frontend/js/chat.js; node --check frontend/js/main.js; node --check frontend/js/settings.js; node tests/frontend_contracts.test.mjs — PASS_REAL, all syntax checks exited 0 and frontend API contract checks passed.
- Browser privacy guard — PASS_REAL, zero external request attempts, zero unauthenticated data requests, and zero uncaught JavaScript errors. The rejected endpoint change produces one expected Chromium console resource message for HTTP 409; no other console errors were accepted.
- Patch whitespace: git diff --check — PASS_REAL, exit 0.

Pre-fix reproductions confirmed the issues: the old parser rejected the valid coalesced chunk as over limit, and temporarily omitting the view-switch abort left the synthetic upstream stream open after navigation. Linux, hosted CI, real provider compatibility, and live credential-vault behavior remain NOT_TESTED. No dependencies or schema changed; existing security, ownership, transport, and credential tests remain enabled and passed.

### Focused differential security review

Risk reviewed: HIGH for credential destination changes; MEDIUM for browser stream lifecycle. The baseline service stored stripped connection URLs directly at connection creation/update (A1-G commit f2b37de3); the current diff adds validation and does not remove existing owner checks. The two route call sites still enter the same service methods. Endpoint parsing is side-effect-free, the error sent to the Models UI is static, and a stored credential blocks any normalized scheme/host/port change before configuration mutation or commit. The credential query remains scoped by user and connection identity.

The Chat parser has one call site in sendMessage. The revised loop measures each extracted frame and residual in UTF-8 bytes while preserving request-ID handling, output limits, and the existing TextDecoder stream mode. switchView has six callers across navigation, keyboard navigation, startup, and search; its new guard only aborts when leaving an active Chat view. Focused tests exercise the attacked inputs and the complete browser suite exercises stream closure and follow-up requests. No uncovered bypass was found in the changed paths. Confidence is limited to the tested Windows/local runtime and synthetic provider boundary; real-provider and Linux behavior remain NOT_TESTED.

## A1-H final integration and release-readiness — 2026-11-18

The configured provider base URL now uses the accepted endpoint parser with `allow_query=False`, matching transport validation before persistence. The validation response is static and does not echo URL contents. Focused create/update regressions cover query strings, fragments, embedded credentials, malformed endpoints, valid API path prefixes, same-origin edits, credentialed origin changes, credential persistence/redaction, and the no-DNS configuration path. The test-first query cases failed before the fix (create returned 201; update returned 200); afterward `tests/test_model_settings.py` passed 22 tests.

Verification on Windows 11, Python 3.11.7 and 3.12.10, with deterministic synthetic provider/network fixtures:

- `python -m pytest -p no:cacheprovider -m 'not browser' -q -rs --tb=short`: PASS_REAL, 370 passed, 9 deselected on each Python version. Three existing Pydantic deprecation warnings appeared on both versions; Python 3.12 also reported an existing tarfile deprecation warning.
- `AURA_RUN_BROWSER=1 python -m pytest -p no:cacheprovider -m browser tests/browser/test_frontend_smoke.py -q -rs --tb=short --basetemp <system-temp-path>`: PASS_REAL, 9 passed. The real FastAPI application and browser were exercised; provider behavior was synthetic. Browser guard recorded zero external request attempts, zero unauthenticated data requests, and zero uncaught JavaScript errors. Three console entries were expected blocked-icon resource messages and the tested HTTP 409 credential-origin rejection.
- `tests/test_model_settings.py`: PASS_REAL, 22 passed; three existing Pydantic deprecation warnings.
- `python -m compileall -q backend tests scripts`: PASS_REAL on Python 3.11.7 and 3.12.10.
- `python -m ruff check backend tests scripts --select E4,E7,E9,F`: PASS_REAL on both versions; `All checks passed!`.
- `python -m pip check`: PASS_REAL on both versions; `No broken requirements found.`
- `node --check` for each of the 12 `frontend/js/*.js` files and `node tests/frontend_contracts.test.mjs`: PASS_REAL; frontend API contract checks passed.
- `git diff --check`: PASS_REAL.

Integration audit found blockers that cannot be corrected within this round's no-new-features and no-provider-adapters boundaries. First, the approved architecture/plan names five network/chat provider implementations plus the local Sentence Transformers compatibility adapter, while current functional adapters are only Ollama and OpenAI-compatible. Second, a synthetic source-path probe of the real `ChatService.process_chat` method showed that when no Chat role is selected but the configured legacy model path exists, `detect_intent` still invokes `LLM.generate` before the no-model/provider fallback. The probe stubbed `LLM.generate`; it initialized no model and made no network request. Related legacy calls remain in Chat, intent, routine, and RAG services. These findings are recorded as blockers, not fixed here, because adding adapters or changing Chat/legacy migration is explicitly out of scope.

No Ollama server was listening at the configured loopback address; no provider inference or cloud calls were made. Real model inference, cloud compatibility, hosted CI, Linux/Docker execution, live Windows Credential Manager persistence, reduced-motion/accessibility-specific runtime coverage, and a real local Ollama integration are NOT_TESTED. Docker's Linux daemon was unavailable. No dependency, schema, route, or frontend changes were made in A1-H.

The pre-existing untracked `docs/evidence/a1-model-providers.zip` was preserved unchanged and unstaged; SHA-256 remained `83E5DA7E602CC8DD2CFA090D46A3828FFB9F44163478B60726BA605B28AB115F`. Task-owned browser and compile cache outputs were confined to verified system-temp paths and removed. Existing repository caches and uncertain artifacts were preserved.

## A1-H-R1 legacy-inference correction — 2026-11-18

Owner clarification: the functional A1 provider scope for PR readiness is exactly Ollama and OpenAI-compatible. Anthropic, Gemini, legacy GGUF adapter integration, and Sentence Transformers integration are deferred and are not A1 PR blockers. The earlier A1-H paragraph that treated those deferred adapters as a blocker is superseded by this scope clarification; its historical record is retained. The actual Chat legacy-inference defect reported there was reproduced and fixed in R1.

`ChatService.process_chat` now treats a missing Chat-role selection as authoritative: deterministic schedule routing may run, explicit task requests that need interpretation receive a safe unavailable response, and all other messages receive the exact no-model fallback. It no longer calls `detect_intent` or the legacy general/knowledge handlers in this state, whether or not a legacy model file exists. The pre-provider path no longer uses intent classification for task creation or RAG/legacy generation for knowledge queries. With a selected role, ordinary Chat uses only that selected provider/model; provider errors remain safe errors and never fall back to GGUF. The streaming route shares the safe pre-provider action behavior and keeps its existing no-role fallback. User/task ownership, confirmations, history behavior, and inert tool proposals are unchanged.

New FastAPI regression cases instrument `detect_intent`, `llm.generate`, `llm.embed`, `_load_llm`, and `_load_embeddings`. They cover no-role task and general/knowledge messages with and without a synthetic legacy-file marker; deterministic schedule handling; selected-provider success and failure; and streaming no-role and selected-provider-failure behavior. Task cases assert that no task is created. Synthetic provider behavior uses the established fake transport; the placeholder legacy file contains only text and is created under the isolated test fixture directory.

Test-first evidence: `python -m pytest -p no:cacheprovider tests/test_chat_streaming.py -q -rs --tb=short -k 'task_request_without_chat_role or general_chat_without_role or stream_without_chat_role'` reported 9 failed, 1 passed, 12 deselected before the production change. Failures showed intent/generation calls for task messages, the knowledge shortcut, and the configured legacy-file path. After correction, `python -m pytest -p no:cacheprovider tests/test_chat_streaming.py -q -rs --tb=short` passed 22 tests. A first post-edit test run also exposed a spy setup error because the corrected service no longer exports `detect_intent`; the helper was adjusted to watch the intent-service boundary, after which the focused suite passed.

Verification on Windows, Python 3.11.7 and 3.12.10:

- `python -m pytest -p no:cacheprovider -m 'not browser' -q -rs --tb=short`: PASS_REAL, 383 passed and 9 deselected on both versions. Python 3.11 emitted 3 existing Pydantic deprecation warnings; Python 3.12 emitted those 3 plus the existing tarfile deprecation warning.
- PowerShell browser invocation: `$env:AURA_RUN_BROWSER='1'; $env:AURA_BROWSER_EVIDENCE_DIR='C:\Users\abhis\AppData\Local\Temp\a1h-r1-browser-0e5a1683d1b34169905837af3358e29f\evidence'; $env:AURA_CAPTURE_VIDEO='0'; & 'C:\Users\abhis\AppData\Local\Temp\aura-a1d-checks-1794898204120\py311\Scripts\python.exe' -m pytest -p no:cacheprovider -m browser tests/browser/test_frontend_smoke.py -q -rs --tb=short --basetemp 'C:\Users\abhis\AppData\Local\Temp\a1h-r1-browser-0e5a1683d1b34169905837af3358e29f'`: PASS_REAL, 9 passed. Guard evidence recorded zero external attempts, zero unauthenticated data requests, and zero uncaught JavaScript errors. Two blocked icon resource messages and the expected HTTP 409 origin-change message appeared in console records. The test also exercises reduced-motion behavior.
- The corresponding Python 3.12 browser invocation collected 9 skips because Playwright is not installed in that venv; browser tests on Python 3.12 are NOT_TESTED. No dependency was installed.
- `python -m pytest -p no:cacheprovider tests/test_chat_streaming.py -q -rs --tb=short`: PASS_REAL on Python 3.11, 22 passed.
- `python -m compileall -q backend tests scripts`, `python -m ruff check backend tests scripts --select E4,E7,E9,F`, and `python -m pip check`: PASS_REAL on both versions.
- `node --check` for all 12 `frontend/js/*.js` files and `node tests/frontend_contracts.test.mjs`: PASS_REAL.
- `git diff --check`: PASS_REAL.

No real providers, cloud services, credentials, or model weights were used. No dependency, schema, route, or frontend change was made. Browser and compile outputs were written to task-specific system-temp paths; the network-guard record was inspected before cleanup.
