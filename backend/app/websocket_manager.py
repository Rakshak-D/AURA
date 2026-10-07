import asyncio
from collections import defaultdict
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass

from fastapi import WebSocket

from .config import config


@dataclass
class _OutboundItem:
    message: str
    acknowledgement: asyncio.Future


@dataclass
class _ConnectionState:
    queue: asyncio.Queue
    sender_task: asyncio.Task


class ConnectionManager:
    def __init__(self):
        self.active_connections: defaultdict[int, set[WebSocket]] = defaultdict(set)
        self.connection_users: dict[WebSocket, int] = {}
        self._states: dict[WebSocket, _ConnectionState] = {}
        self.loop = None

    def set_loop(self, loop):
        self.loop = loop

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        queue = asyncio.Queue(maxsize=config.websocket_outbound_queue_size)
        sender_task = asyncio.create_task(self._sender_loop(websocket, queue))
        self.active_connections[user_id].add(websocket)
        self.connection_users[websocket] = user_id
        self._states[websocket] = _ConnectionState(queue, sender_task)

    async def _sender_loop(self, websocket: WebSocket, queue: asyncio.Queue):
        try:
            while True:
                item: _OutboundItem = await queue.get()
                try:
                    if item.acknowledgement.done():
                        continue
                    await asyncio.wait_for(
                        websocket.send_text(item.message),
                        timeout=config.reminder_delivery_timeout_seconds,
                    )
                    if not item.acknowledgement.done():
                        item.acknowledgement.set_result(True)
                except asyncio.CancelledError:
                    if not item.acknowledgement.done():
                        item.acknowledgement.set_result(False)
                    raise
                except Exception:
                    if not item.acknowledgement.done():
                        item.acknowledgement.set_result(False)
                    self.disconnect(websocket, cancel_sender=False)
                    return
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            self._fail_queued_items(queue)
            raise

    @staticmethod
    def _fail_queued_items(queue: asyncio.Queue):
        while not queue.empty():
            item = queue.get_nowait()
            if not item.acknowledgement.done():
                item.acknowledgement.set_result(False)
            queue.task_done()

    def disconnect(self, websocket: WebSocket, *, cancel_sender: bool = True):
        user_id = self.connection_users.pop(websocket, None)
        state = self._states.pop(websocket, None)
        if user_id is not None:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        if state is not None:
            self._fail_queued_items(state.queue)
            try:
                current_task = asyncio.current_task()
            except RuntimeError:
                # Synchronous callers (including scheduler/test cleanup) may
                # run outside an event loop.
                current_task = None
            if cancel_sender and state.sender_task is not current_task:
                state.sender_task.cancel()

    async def shutdown(self):
        tasks = [state.sender_task for state in self._states.values()]
        for websocket in list(self.connection_users):
            self.disconnect(websocket)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._states.clear()

    async def broadcast(self, message: str, user_id: int) -> bool:
        if len(message.encode("utf-8")) > config.websocket_max_message_bytes:
            return False
        connections = list(self.active_connections.get(user_id, set()))
        if not connections:
            return False
        acknowledgements = []
        try:
            for connection in connections:
                state = self._states.get(connection)
                if state is None:
                    continue
                acknowledgement = asyncio.get_running_loop().create_future()
                item = _OutboundItem(message, acknowledgement)
                try:
                    state.queue.put_nowait(item)
                except asyncio.QueueFull:
                    acknowledgement.set_result(False)
                    self.disconnect(connection)
                acknowledgements.append(acknowledgement)

            pending = set(acknowledgements)
            while pending:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                if any(ack.result() is True for ack in done):
                    return True
            return False
        except asyncio.CancelledError:
            for acknowledgement in acknowledgements:
                if not acknowledgement.done():
                    acknowledgement.set_result(False)
            raise

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
