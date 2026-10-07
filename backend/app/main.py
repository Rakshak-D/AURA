import logging

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import config
from .database import init_db
from .routes import (
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
    allow_origins=["*"],
    allow_credentials=True,
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
    await manager.connect(websocket)
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
