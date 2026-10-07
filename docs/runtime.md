# AURA Runtime Provisioning

## Supported environment

AURA targets Python 3.10 or newer. The core API is usable on CPU-only machines and does not require a GGUF model, CUDA, SentenceTransformers, ChromaDB, OCR binaries, or user documents to import or start.

## Install profiles

From the repository root:

    python -m pip install -r requirements.txt

This installs the core API, SQLite/SQLAlchemy, scheduler, and rate-limit runtime. Optional capabilities are separate:

    python -m pip install -r requirements-ai.txt
    python -m pip install -r requirements-rag.txt

The AI profile installs llama.cpp. The RAG profile installs SentenceTransformers, ChromaDB, and document/OCR libraries. These packages do not provision model artifacts.

## Configuration and canonical paths

Copy .env.example to .env and edit only the local copy. backend.app.config.Settings is the single configuration boundary. By default:

- LLM: models/phi-3-mini-4k-instruct-q4.gguf
- embeddings: models/embeddings/all-MiniLM-L6-v2
- embedding cache: models/embedding-cache
- database, uploads, logs, and Chroma: under backend/data/

Use MODEL_FILENAME, EMBEDDING_MODEL, DATA_DIR, MODELS_DIR, DB_PATH, CHROMA_PATH, UPLOADS_DIR, and LOGS_DIR only through environment configuration. The downloader and runtime use the same Settings paths.

## Model provisioning

The supported artifact metadata is in backend/model_manifest.json. The current upstream references do not provide an authoritative checksum verified by this repository, so the manifest deliberately contains no invented SHA-256. The provisioning tool always calculates and reports the local SHA-256, but reports the artifact as unverified until an authoritative checksum is added.

Inspect capability status without loading models:

    python backend/download_models.py --status

Provision the LLM explicitly:

    python backend/download_models.py

Verify the existing LLM artifact:

    python backend/download_models.py --verify

An existing file is never overwritten automatically. Downloads stream into a .part file and are atomically finalized only after transfer and available integrity checks succeed. Failed downloads remove the .part file and return a non-zero exit status.

## Embedding provisioning

Embedding provisioning is explicit:

    python backend/download_models.py --embedding

This is the only documented command that may ask SentenceTransformers/Hugging Face to download the embedding model. Normal API import, startup, health checks, and readiness checks do not download or load it. Once provisioned, the runtime loads only the canonical local directory.

## CPU and GPU

CPU mode is the default:

    USE_GPU=false
    N_GPU_LAYERS=0

GPU mode must be requested explicitly and requires a compatible local AI stack:

    USE_GPU=true
    N_GPU_LAYERS=32

The validator rejects negative GPU-layer values; use a non-negative explicit layer count. /ready reports whether GPU was requested, whether the Python runtime can see CUDA, and whether the optional runtime is installed. It does not install CUDA/PyTorch or make CPU mode fail.

## Health and readiness

GET /health is a lightweight liveness check. It does not load LLM/embeddings, initialize Chroma, access the network, or download anything.

GET /ready checks core database readiness and reports optional LLM, embedding, RAG, and scheduler capability states. Missing optional artifacts/dependencies do not make core readiness fail. GET /diagnostics/rag reports RAG capability without creating a Chroma store.

Capability states include ready, artifact_missing, artifact_unverified, optional_dependency_missing, not_initialized, available_not_initialized, and runtime_failure. Detailed local paths and secrets are not returned by the endpoints.
