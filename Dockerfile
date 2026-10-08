# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
COPY requirements.txt requirements-ai.txt requirements-rag.txt ./
RUN pip install --no-cache-dir -r requirements.txt

FROM builder AS ai_venv
RUN pip install --no-cache-dir -r requirements-ai.txt

FROM ai_venv AS rag_venv
RUN pip install --no-cache-dir -r requirements-rag.txt

FROM builder AS runtime-base

ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd --gid "$APP_GID" aura \
    && useradd --uid "$APP_UID" --gid "$APP_GID" --create-home --shell /usr/sbin/nologin aura \
    && mkdir -p /opt/aura /var/lib/aura/data /var/lib/aura/models \
    && chown -R aura:aura /opt/aura /var/lib/aura

WORKDIR /opt/aura
COPY --chown=aura:aura backend ./backend
COPY --chown=aura:aura frontend ./frontend
COPY --chown=aura:aura scripts ./scripts

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/opt/aura \
    ENVIRONMENT=production \
    HOST=0.0.0.0 \
    PORT=8000 \
    RELOAD=false \
    DATA_DIR=/var/lib/aura/data \
    MODELS_DIR=/var/lib/aura/models \
    DB_PATH=/var/lib/aura/data/aura.db \
    CHROMA_PATH=/var/lib/aura/data/chroma_db \
    UPLOADS_DIR=/var/lib/aura/data/uploads \
    LOGS_DIR=/var/lib/aura/data/logs

USER aura
EXPOSE 8000

# The single-process command is intentional: SQLite, the scheduler, and the
# process-local WebSocket manager are not a multi-worker deployment model.
ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-server-header"]

# Optional targets reuse the exact same application image and only replace the
# virtual environment. The default `runtime` target remains CPU-only/core-only.
FROM runtime-base AS runtime

FROM runtime-base AS ai
COPY --from=ai_venv /opt/venv /opt/venv

FROM ai AS full
COPY --from=rag_venv /opt/venv /opt/venv
USER root
RUN apt-get update \
    && apt-get install --no-install-recommends -y tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
USER aura
