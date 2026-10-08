# AURA

AURA (Augmented Understanding And Response Agent) is a self-hosted personal
productivity assistant. It combines authenticated task and reminder management,
calendar scheduling, document search, local AI capabilities, and browser
notifications in one FastAPI application.

Repository: <https://github.com/Rakshak-D/AURA>

## Current capabilities

- Local username/password authentication with short-lived bearer tokens.
- User-owned tasks, routines, reminders, calendar scheduling, search, settings,
  and logical data export.
- Persistent reminder delivery through the database-backed scheduler and
  authenticated WebSocket notifications.
- Document upload and user-scoped RAG when the optional RAG dependencies and
  provisioned embedding/Chroma runtime are available.
- Optional local GGUF inference through llama.cpp. The core API does not load or
  download a model during import or startup.
- Browser-only voice input through the Web Speech API. AURA does not provide a
  backend speech-to-text service.
- A vanilla JavaScript frontend with safe text rendering and a centralized
  authenticated API client.

Chat currently returns a completed response. The repository does not claim
server-side chat streaming or exactly-once reminder delivery.

## Architecture

The application is intentionally a single-host, single-process deployment:

```text
Browser HTML/CSS/JavaScript
        | HTTP + authenticated WebSocket
        v
FastAPI/Uvicorn application
  |-- SQLAlchemy -> SQLite (source of truth)
  |-- APScheduler -> persistent reminder polling
  |-- optional llama.cpp -> local GGUF model
  |-- optional SentenceTransformers/Chroma -> user-scoped RAG
  `-- authenticated WebSocket manager -> browser notifications
```

SQLite, the scheduler, and WebSocket connection state are process-local. Run
one application worker; multiple workers or replicas are not supported.

## Technology stack

- Python 3.11 (Python 3.10+ is supported by the current code)
- FastAPI, Uvicorn, Pydantic Settings, SQLAlchemy, SQLite
- APScheduler and authenticated WebSockets
- Vanilla JavaScript, HTML, CSS, Chart.js, and Lucide icons in the frontend
- Optional: llama-cpp-python for local LLM inference
- Optional: SentenceTransformers, ChromaDB, document parsers, and OCR support

## Local development

Prerequisites: Python 3.11, a modern browser, and a writable local data
directory. The core install is CPU-only and does not need CUDA, a GGUF model,
embedding downloads, ChromaDB, OCR, or user documents.

```bash
git clone https://github.com/Rakshak-D/AURA.git
cd AURA
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
copy .env.example .env  # Windows; use cp on Linux/macOS
python backend/run_backend.py
```

Open <http://127.0.0.1:8000>. Register a local account before using protected
features. Use a unique `AUTH_SECRET_KEY` for anything beyond local development;
production settings reject the development placeholder.

Optional capabilities are deliberately separate:

```bash
python -m pip install -r requirements-ai.txt
python -m pip install -r requirements-rag.txt
python backend/download_models.py --status
```

Provision model artifacts explicitly with `backend/download_models.py`; API
startup never downloads them. See [docs/runtime.md](docs/runtime.md) for
canonical paths, CPU/GPU behavior, model verification, and capability states.

## Docker deployment

For a persistent single-host deployment, copy `.env.example` to an untracked
`.env`, set a strong `AUTH_SECRET_KEY`, and run:

```bash
docker compose build
docker compose up -d
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

The default Compose binding is localhost-only. The `tls` profile adds the
checked-in Caddy reverse proxy for an explicitly configured domain; it does not
make public certificate or DNS claims. Models are stored separately and are
never baked into the image or downloaded at container startup.

Back up and restore through the running container's persistent data paths:

```bash
docker compose exec -T aura python scripts/backup.py backup /tmp/aura-backup.tar.gz
docker cp "$(docker compose ps -q aura):/tmp/aura-backup.tar.gz" ./aura-backup.tar.gz
```

The archive contains SQLite, uploads, and Chroma data when present, but not
models, `.env` files, or secrets. The complete restore procedure is in
[docs/deployment.md](docs/deployment.md).

## Project structure

```text
AURA/
├── backend/                 FastAPI app, models, services, and model tooling
├── frontend/                Vanilla HTML/CSS/JavaScript application
├── docs/                    Runtime, security, database, testing, and deployment docs
├── scripts/                 Backup and deployment smoke-test utilities
├── tests/                   Python, contract, security, and browser tests
├── Dockerfile               CPU-only runtime plus optional AI/RAG targets
├── docker-compose.yml       Local single-host deployment and optional TLS profile
├── Caddyfile                Reverse-proxy configuration for the TLS profile
├── requirements*.txt        Core, development, browser, AI, and RAG dependency sets
└── .github/workflows/       CI and deployment validation
```

## Testing and CI

Install the development requirements and run the deterministic suite:

```bash
python -m pytest -m "not browser" -q
python -m compileall -q backend tests scripts
python -m ruff check backend tests scripts --select E4,E7,E9,F
python -m pip check
node tests/frontend_contracts.test.mjs
```

Browser tests use Playwright and are separate from the default model-free
suite:

```bash
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
# PowerShell: $env:AURA_RUN_BROWSER = "1"
python -m pytest -m browser -q
```

GitHub Actions runs Python tests and coverage, repository-wide core Ruff
checks, Python compilation, dependency checks, frontend syntax/security checks,
Playwright regressions, and a CPU-only Docker deployment smoke test.

## Operational limitations

- AURA is designed for one host and one Uvicorn worker. SQLite, the scheduler,
  and WebSocket connections are not coordinated across replicas.
- Reminder delivery is at-least-once. A crash after notification dispatch and
  before the `sent` update can produce a duplicate.
- Local LLM and RAG support is optional and requires separately provisioned
  artifacts and, for OCR, system dependencies.
- Browser voice input depends on browser/platform Web Speech support and user
  microphone permission.
- The default deployment is suitable for localhost or deliberate LAN use. A
  public deployment requires HTTPS, firewall controls, a strong secret, and
  explicit allowed origins.

More detail is available in [docs/runtime.md](docs/runtime.md),
[docs/authentication.md](docs/authentication.md),
[docs/websocket.md](docs/websocket.md),
[docs/web-security.md](docs/web-security.md), and
[docs/testing.md](docs/testing.md).

## License

AURA is released under the MIT License. See [LICENSE](LICENSE).
