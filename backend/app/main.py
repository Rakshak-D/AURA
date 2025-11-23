from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
from .config import config
from .database import init_db
from .routes import chat, tasks, upload, dashboard, reminders, search, export, schedule, insights
from .services.reminder_service import start_scheduler, scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("--- 1. Initializing Database ---")
    init_db()
    print("--- 2. Starting Scheduler ---")
    start_scheduler()
    print("--- 3. Aura Backend Ready ---")
    yield
    if scheduler.running:
        scheduler.shutdown()

app = FastAPI(title="AURA", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(reminders.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(schedule.router, prefix="/api")
app.include_router(insights.router, prefix="/api/insights")

app.mount("/static", StaticFiles(directory=str(config.FRONTEND_DIR)), name="static")

@app.get("/")
async def root():
    return FileResponse(str(config.FRONTEND_DIR / "index.html"))