import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import authenticate_websocket
from .config import config
from .database import SessionLocal, init_db
from .routes import (
    auth,
    chat,
    dashboard,
    export,
    health,
    insights,
    reminders,
    routine,
    schedule,
    search,
    settings,
    tasks,
    upload,
)
from .runtime_diagnostics import startup_summary
from .services.reminder_service import (
    recover_stale_reminders,
    start_scheduler,
    stop_scheduler,
)
from .websocket_manager import manager

app = FastAPI(title="AURA API", version="1.0.0")
WEBSOCKET_PROTOCOL_VERSION = 1


def _ws_envelope(message_type: str, data: dict | None = None) -> dict:
    return {
        "protocol_version": WEBSOCKET_PROTOCOL_VERSION,
        "type": message_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' https://unpkg.com https://cdn.jsdelivr.net 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
        )
        if request.url.path.startswith("/api/auth"):
            response.headers["Cache-Control"] = "no-store"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.getLogger(__name__).exception("Unhandled application error")
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error"},
    )

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    config.init_dirs()
    config.setup_logging()
    # Initialize DB
    init_db()
    if config.environment != "test" and config.reminder_scheduler_enabled:
        try:
            recover_stale_reminders()
            start_scheduler()
        except RuntimeError:
            logging.getLogger(__name__).warning(
                "Reminder scheduler unavailable; persistent reminders remain in SQLite"
            )
    logging.getLogger(__name__).info("Serving static files from %s", config.frontend_dir)
    logging.getLogger(__name__).info("Capability summary: %s", startup_summary())
    
    import asyncio
    manager.set_loop(asyncio.get_running_loop())


@app.on_event("shutdown")
async def shutdown_event():
    stop_scheduler()
    await manager.shutdown()

# Routers
app.include_router(chat.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(reminders.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(schedule.router, prefix="/api")
app.include_router(insights.router, prefix="/api/insights")
app.include_router(settings.router, prefix="/api")
app.include_router(routine.router, prefix="/api")
app.include_router(health.router)

# Static Files
app.mount("/static", StaticFiles(directory=str(config.FRONTEND_DIR)), name="static")

# WebSocket
@app.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket):
    db = SessionLocal()
    try:
        user = await authenticate_websocket(websocket, db)
        await manager.connect(websocket, user.id)
        await websocket.send_json(_ws_envelope(
            "ready",
            {"heartbeat_interval_seconds": config.websocket_heartbeat_interval_seconds},
        ))
    except Exception:
        manager.disconnect(websocket)
        db.close()
        return
    db.close()
    try:
        while True:
            try:
                raw_message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=config.websocket_heartbeat_interval_seconds * 2,
                )
            except asyncio.TimeoutError:
                await websocket.close(code=1001, reason="heartbeat timeout")
                break
            if len(raw_message.encode("utf-8")) > config.websocket_max_message_bytes:
                await websocket.send_json(_ws_envelope("error", {"code": "message_too_large"}))
                await websocket.close(code=1009, reason="message too large")
                break
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json(_ws_envelope("error", {"code": "invalid_json"}))
                await websocket.close(code=1003, reason="invalid message")
                break
            if not isinstance(message, dict) or message.get("type") not in {"ping", "pong"}:
                await websocket.send_json(_ws_envelope("error", {"code": "unknown_message_type"}))
                await websocket.close(code=1003, reason="unsupported message")
                break
            if message["type"] == "ping":
                await websocket.send_json(_ws_envelope("pong"))
    except WebSocketDisconnect:
        pass
    except Exception:
        logging.getLogger(__name__).warning("WebSocket connection closed unexpectedly")
    finally:
        manager.disconnect(websocket)

@app.get("/")
async def root():
    return FileResponse(str(config.FRONTEND_DIR / "index.html"))
