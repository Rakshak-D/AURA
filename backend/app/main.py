import logging

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
from .websocket_manager import manager

app = FastAPI(title="AURA API", version="1.0.0")


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
    logging.getLogger(__name__).info("Serving static files from %s", config.frontend_dir)
    logging.getLogger(__name__).info("Capability summary: %s", startup_summary())
    
    import asyncio
    manager.set_loop(asyncio.get_running_loop())

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
    except Exception:
        db.close()
        return
    db.close()
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        logging.getLogger(__name__).exception("WebSocket error")
        manager.disconnect(websocket)

@app.get("/")
async def root():
    return FileResponse(str(config.FRONTEND_DIR / "index.html"))
