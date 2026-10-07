# Testing and CI

AURA's default test suite is isolated and CPU-only. It uses temporary SQLite
databases and temporary runtime directories for every test. It does not use
`data/aura.db`, the checked-out `models` directory, persistent Chroma data,
GPU libraries, model downloads, or external AI services.

Route-focused `TestClient` tests intentionally replace the startup database
initializer with a no-op after binding all database boundaries to the isolated
engine; this avoids creating production defaults while still exercising the
real request dependency, authentication, and shutdown lifecycle. Startup
behavior itself is covered separately by the subprocess foundation test with
an explicit temporary `DATA_DIR`.

## Local commands

Install the core and development dependencies:

```text
python -m pip install -r requirements-dev.txt
python -m pytest -m "not browser" --cov=backend.app
python -m compileall -q backend tests
python -m ruff check backend tests
python -m pip check
```

Tests are tagged with `unit`, `api`, `integration`, `security`, `websocket`,
`rag`, `ai`, and `browser`. The default suite excludes browser tests but runs
the deterministic integration tests. Use `-m "not browser and not
integration"` when a faster unit/API-only loop is useful.

## Browser tests

Browser tests use Playwright and a deterministic local HTTP mock; they do not
need a real model or external network service:

```text
python -m pip install -r requirements-dev.txt -r requirements-browser.txt
python -m playwright install chromium
$env:AURA_RUN_BROWSER = "1"  # PowerShell
python -m pytest -m browser -q
```

The CI browser job installs Chromium with system dependencies and runs the
same tests. Browser coverage is intentionally separate from the required
lightweight Python path.

## CI jobs

`.github/workflows/ci.yml` contains three jobs:

- Python tests, coverage, compileall, Ruff, and `pip check`.
- Frontend JavaScript syntax and static security checks.
- Playwright browser regressions, with the browser job depending on the first
  two jobs and preserving failure artifacts when present.

No CI job installs `requirements-ai.txt` or `requirements-rag.txt`, and the
default job has no path that downloads GGUF or embedding models.

## Troubleshooting

If browser dependencies are unavailable locally, run the default suite and
use the CI browser job for the maintained Chromium environment. Integration
tests that require optional local model/RAG packages remain explicitly
separable and must use deterministic fakes or isolated temporary storage.
