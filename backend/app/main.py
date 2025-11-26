    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
# Apply rate limit to chat router (needs to be done on the router or endpoints)
# Since we imported the router, we can't easily decorate it here without modifying chat.py
# or wrapping it.
# Let's modify chat.py to accept the limiter, or better, just add it to the app state and use it in chat.py?
# Actually, slowapi works best with decorators on endpoints.
# I will modify chat.py to use the limiter.
# But I need to pass the limiter instance.
# A common pattern is to define limiter in a separate file (e.g. extensions.py or security.py) and import it.
# Let's put limiter in security.py or a new file.
# For now, I'll put it in security.py to avoid circular imports if I import it in main.

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

app.mount("/static", StaticFiles(directory=str(config.FRONTEND_DIR)), name="static")

@app.websocket("/ws/notifications")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)

@app.get("/")
async def root():
    return FileResponse(str(config.FRONTEND_DIR / "index.html"))