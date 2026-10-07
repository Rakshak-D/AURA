import asyncio
from collections import defaultdict
from concurrent.futures import TimeoutError as FutureTimeoutError

from fastapi import WebSocket

from .config import config


class ConnectionManager:
    def __init__(self):
        self.active_connections: defaultdict[int, set[WebSocket]] = defaultdict(set)
        self.connection_users: dict[WebSocket, int] = {}
        self.loop = None

    def set_loop(self, loop):
        self.loop = loop

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.active_connections[user_id].add(websocket)
        self.connection_users[websocket] = user_id

    def disconnect(self, websocket: WebSocket):
        user_id = self.connection_users.pop(websocket, None)
        if user_id is not None:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def broadcast(self, message: str, user_id: int) -> bool:
        delivered = False
        for connection in list(self.active_connections.get(user_id, set())):
            try:
                await connection.send_text(message)
                delivered = True
            except Exception:
                self.disconnect(connection)
        return delivered

    def broadcast_sync(self, message: str, user_id: int):
        if not self.loop or not self.active_connections.get(user_id):
            return False
        future = asyncio.run_coroutine_threadsafe(
            self.broadcast(message, user_id), self.loop
        )
        try:
            return bool(future.result(timeout=config.reminder_delivery_timeout_seconds))
        except FutureTimeoutError:
            future.cancel()
            return False
        except Exception:
            future.cancel()
            return False


manager = ConnectionManager()
