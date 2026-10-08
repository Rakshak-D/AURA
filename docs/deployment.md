# AURA deployment

AURA is designed for a single host and one application process. SQLite, the
reminder scheduler, and WebSocket connections are process-local, so multiple
Uvicorn workers or replicas are not a supported deployment model.

## Prerequisites

- Docker Engine with Compose v2.
- Resources appropriate for the selected feature set. The core API is
  CPU-only; local LLM and embeddings require substantially more memory.
- A strong secret generated outside the repository, for example
  `openssl rand -hex 32`.

The base image contains only core API dependencies. It does not contain a GGUF
model, CUDA, SentenceTransformers, ChromaDB, OCR binaries, or test tools.

## Base deployment

Create a local `.env` from `.env.example`, then set at least:

```dotenv
AUTH_SECRET_KEY=<unique-random-value-at-least-32-characters>
ALLOWED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
```

For environments that provide Docker secrets, use the optional
`docker-compose.secrets.yml` override. It reads the external secret through
`AUTH_SECRET_KEY_FILE` and never places its value in Compose YAML or logs:

```bash
printf '%s' "$(openssl rand -hex 32)" | docker secret create aura_auth_secret -
docker compose -f docker-compose.yml -f docker-compose.secrets.yml up -d
```

If Docker secrets are not available, inject `AUTH_SECRET_KEY` through the
runtime environment or an untracked `.env` file. Production rejects missing,
short, or placeholder authentication secrets.

Start the default localhost-only service:

```bash
docker compose build
docker compose up -d
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
```

Compose publishes only `127.0.0.1:8000` by default. For LAN access, set
`AURA_BIND_ADDRESS` explicitly and use an explicit `ALLOWED_ORIGINS` list. Do
not bind the service publicly without HTTPS, firewall rules, and a strong
secret.

The container runs one Uvicorn worker with reload disabled. `health` is a
liveness probe. `ready` returns HTTP 503 until the database schema and core
writable directories are available. Missing optional AI/RAG artifacts are
reported in the response but do not make the core service unready.

## Persistence

Named volumes preserve state across container replacement:

| Volume | Contents |
| --- | --- |
| `aura_data` | SQLite database, uploads, Chroma data, and application logs |
| `aura_models` | Explicitly provisioned local model/embedding artifacts |
| `caddy_data` / `caddy_config` | TLS profile state only |

The SQLite database is `/var/lib/aura/data/aura.db`; documents are under
`/var/lib/aura/data/uploads`; Chroma, when enabled, is under
`/var/lib/aura/data/chroma_db`. This does not provide multi-host coordination
or exactly-once reminder delivery.

## Optional AI and RAG

AI is intentionally not downloaded or enabled by container startup. The
Dockerfile has optional targets that reuse the same application image:

```bash
docker build --target ai -t aura:ai .
docker build --target full -t aura:ai-rag .
```

Provision artifacts explicitly with the existing downloader; never put models
or credentials in the image:

```bash
python backend/download_models.py --status
python backend/download_models.py
python backend/download_models.py --embedding
python backend/download_models.py --verify
```

An absent model leaves the API available and is visible in `/ready` and startup
logs. The embedding runtime is similarly optional.

## TLS and reverse proxy

The `tls` Compose profile uses Caddy and the checked-in `Caddyfile`:

```bash
AURA_DOMAIN=aura.example.test docker compose --profile tls up -d
```

For a real public domain, point DNS at the host, publish ports 80/443 through
the firewall, and set `ALLOWED_ORIGINS` to the actual HTTPS origin. Caddy's
automatic certificates are not claimed for a deployment without a real domain
and reachable DNS. Localhost mode does not require TLS or public DNS.

## Backup and restore

Use the SQLite backup API rather than copying a live database file:

```bash
ENVIRONMENT=production AUTH_SECRET_KEY="$AUTH_SECRET_KEY" \
  python scripts/backup.py backup /secure/backup/aura-$(date +%F).tar.gz
ENVIRONMENT=production AUTH_SECRET_KEY="$AUTH_SECRET_KEY" \
  python scripts/backup.py restore /secure/backup/aura-2026-10-08.tar.gz
```

The archive contains SQLite, uploads, and Chroma data if present. It excludes
models, `.env` files, and secrets. Stop AURA before restore, verify the archive
on a temporary deployment, and keep an independent copy of model files.

## Operations and limits

```bash
docker compose logs -f aura
docker compose restart aura
docker compose down
```

Schema migrations run during startup and must complete before readiness. The
scheduler and WebSocket manager are process-local. Reminder delivery is
at-least-once, and a crash between delivery and the database update can cause
a duplicate. Do not configure multiple workers or replicas.

The core service needs normal Python/SQLite resources. Local GGUF inference and
SentenceTransformers have model-specific CPU/RAM requirements; measure the
selected artifacts on the target host rather than assuming a fixed minimum.
RAG additionally requires optional document/vector dependencies and persistent
Chroma storage.

## Security checklist

- Keep `AUTH_SECRET_KEY` outside source control and rotate it if exposed.
- Keep the default bind address localhost unless LAN exposure is deliberate.
- Use HTTPS for public access and explicit CORS origins.
- Do not mount the repository, host root, or arbitrary writable directories.
- Do not expose SQLite, uploads, Chroma, or model volumes as HTTP files.
- Review `/ready`, logs, backups, and firewall state after upgrades.
