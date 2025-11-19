from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
import os

# Use relative import for routes
from .routes import chat, upload, tasks, reminders, dashboard
from .services.reminder_service import check_adaptive
from .database import init_db

# Setup Scheduler
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.add_job(lambda: check_adaptive(1), 'interval', hours=1)
    scheduler.start()
    print("--- Scheduler Started ---")
    yield
    scheduler.shutdown()
    print("--- Scheduler Shutdown ---")

app = FastAPI(title="Aura API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(reminders.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")

# --- WebSocket Endpoint (Added) ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        # Keep the connection open
        while True:
            await websocket.receive_text()
    except Exception:
        pass
# ----------------------------------

# Fix static path resolution
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend"))
app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/")
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)