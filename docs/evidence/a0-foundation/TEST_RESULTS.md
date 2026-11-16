# A0 Test and Compatibility Results

## Environment

Both clean environments were created on 64-bit Windows and installed from the declared manifests using the configured PyPI mirror. No application/browser traffic was allowed to non-local hosts by the Playwright suite.

| Environment | Python | Core/test/browser package set | Install and `pip check` |
|---|---|---|---|
| `C:\Users\abhis\AppData\Local\Temp\aura-a0-verify-py311` | 3.11.7 | FastAPI 0.163.1; Starlette 1.10.0; Uvicorn 0.54.0; python-multipart 0.0.33; Pydantic 2.14.3; pydantic-settings 2.16.3; python-dotenv 1.2.4; SQLAlchemy 2.0.57; APScheduler 3.11.3; SlowAPI 0.1.10; PyJWT 2.15.1; pwdlib 0.4.2; pytest 7.4.3; pytest-asyncio 0.21.1; httpx2 2.16.0; pytest-cov 4.1.0; Ruff 0.6.9; Playwright 1.65.2 | `PASS_REAL`; clean `pip check` |
| `C:\Users\abhis\AppData\Local\Temp\aura-a0-verify-py312` | 3.12.10 | Same exact package versions as Python 3.11 | `PASS_REAL`; clean `pip check` |

The clean installs used `pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple --timeout 120 --retries 3 -r requirements-dev.txt -r requirements-browser.txt`. The core runtime pins are also independently listed in `requirements.txt`; optional inference/RAG packages are not required by the core install.

## Test results

| Check | Status | Result / evidence |
|---|---|---|
| Baseline collection | `PASS_SYNTHETIC` | 97 collected before changes; 96 passed and 1 browser test deselected. See `baseline/BASELINE.md`. |
| Final collection, Python 3.11 | `PASS_SYNTHETIC` | 104 collected; `final/py311-collection.txt`. |
| Final backend suite, Python 3.11 | `PASS_SYNTHETIC` | 97 passed, 7 browser tests deselected, 0 failed/skipped/errors; 3 warnings. See `final/py311-backend-tests.txt`. |
| Final collection, Python 3.12 | `PASS_SYNTHETIC` | 104 collected; `final/py312-collection.txt`. |
| Final backend suite, Python 3.12 | `PASS_SYNTHETIC` | 97 passed, 7 browser tests deselected, 0 failed/skipped/errors; 4 warnings. See `final/py312-backend-tests.txt`. |
| Model-free startup/lifespan | `PASS_SYNTHETIC` | The actual FastAPI lifespan ran with isolated temporary directories and confirmed that LLM and Chroma objects were not initialized. Covered by `test_startup_does_not_initialize_model_or_chroma` in both interpreter runs. |
| Windows compatibility | `PASS_REAL` | Both interpreter versions and their full deterministic suites ran on Windows. Python 3.12.10 additionally meets the requested Windows compatibility check. No Linux runtime was exercised locally. |
| Existing security regressions | `PASS_SYNTHETIC` | 50 collected security/authentication/database-integrity/reminder-reliability/web-security tests passed in a focused Python 3.11 run; those tests also passed in each full backend run. See `SECURITY_REGRESSION.md`. |
| Real browser suite | `PASS_REAL` | 7 passed, 97 deselected, 0 failed in 42.02 seconds using Playwright 1.65.2, Chromium, the real local Uvicorn app, temporary SQLite, and no model. See `final/browser-suite.txt`. |
| CI workflow execution | `NOT_TESTED` | Workflow YAML parsed locally; no push or PR was created, so hosted GitHub Actions did not run. |

The browser tests cover actual account registration/sign-in, failure-safe icon initialization, task creation/completion/persistence, graceful no-model Chat, functional navigation and Chart.js rendering, keyboard/focus/touch/layout at five viewport widths, and a recorded user journey. Chat returned the app's actual no-model fallback; this is not a real-LLM test.

## Additional local checks

- `python -m compileall -q backend tests scripts`: passed.
- `python -m ruff check backend tests scripts --select E4,E7,E9,F`: passed.
- `node --check` for the locally vendored Lucide asset and all `frontend/js/*.js`: passed.
- `node tests/frontend_contracts.test.mjs`: passed.
- `.github/workflows/ci.yml` parsed with PyYAML: passed.
- `git diff --check`: passed.
- `python -m pip check` in both clean environments: no broken requirements.

The final pytest runs reported three existing Pydantic class-based `Config` deprecation warnings. Python 3.12 also reported the existing `tarfile.extractall()` future-default warning in `scripts/backup.py:62`. Neither warning caused a failure; these unrelated compatibility cleanups were left outside A0.

The files `final/implementation-iteration-initial-failure.txt` and `final/targeted-browser-checks.txt` preserve intermediate red/diagnostic runs from before the final browser fixes. The authoritative final browser result is `final/browser-suite.txt` and the last seven rows in `final/browser-run-summary.jsonl`.

## A0-R1 corrective rerun

The A0-R1 corrective pass reran both complete deterministic backend suites and the complete real-browser suite after the Chat fallback, narrow composer, and CI trigger updates. Exact commands, individual durations, and new evidence files are in `A0_R1_REVIEW.md`.
