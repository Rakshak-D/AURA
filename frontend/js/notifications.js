// Authenticated reminder notification client. The bearer token is exchanged
// for a short-lived, single-use WebSocket ticket and is never put in the URL.
class AuraNotificationClient {
    constructor() {
        this.socket = null;
        this.stopped = true;
        this.reconnectTimer = null;
        this.heartbeatTimer = null;
        this.retry = 0;
        this.dedup = new Map();
        this.maxRetryDelay = 30000;
    }

    start() {
        if (!getAuthToken()) return;
        this.stopped = false;
        if (!this.socket || this.socket.readyState === WebSocket.CLOSED) this.connect();
    }

    stop() {
        this.stopped = true;
        clearTimeout(this.reconnectTimer);
        clearInterval(this.heartbeatTimer);
        this.reconnectTimer = null;
        this.heartbeatTimer = null;
        if (this.socket) {
            this.socket.onclose = null;
            this.socket.close(1000, 'logout');
            this.socket = null;
        }
        this.retry = 0;
    }

    async connect() {
        if (this.stopped || this.socket?.readyState === WebSocket.OPEN || this.socket?.readyState === WebSocket.CONNECTING) return;
        const response = await apiFetch(`${API_URL}/auth/ws-ticket`, { method: 'POST' });
        if (!response.ok || this.stopped) return;
        const body = await response.json();
        if (typeof body.ticket !== 'string' || !body.ticket) return this.scheduleReconnect();
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.socket = new WebSocket(`${protocol}//${window.location.host}/ws/notifications?ticket=${encodeURIComponent(body.ticket)}`);
        this.socket.onopen = () => { this.retry = 0; };
        this.socket.onmessage = (event) => this.handleMessage(event.data);
        this.socket.onerror = () => this.socket?.close();
        this.socket.onclose = () => {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
            this.socket = null;
            this.scheduleReconnect();
        };
    }

    scheduleReconnect() {
        if (this.stopped || this.reconnectTimer) return;
        const delay = Math.min(1000 * (2 ** this.retry), this.maxRetryDelay);
        this.retry = Math.min(this.retry + 1, 5);
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, delay);
    }

    handleMessage(raw) {
        let message;
        try { message = JSON.parse(raw); } catch (error) { return this.socket?.close(1003, 'invalid protocol'); }
        if (!message || message.protocol_version !== 1 || typeof message.type !== 'string') return this.socket?.close(1003, 'invalid protocol');
        if (message.type === 'ready') {
            const interval = Number(message.data?.heartbeat_interval_seconds);
            if (!Number.isFinite(interval) || interval <= 0) return this.socket?.close(1003, 'invalid heartbeat');
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = setInterval(() => this.sendPing(), interval * 1000);
            return;
        }
        if (message.type === 'pong') return;
        if (message.type === 'error') return showToast('Notification connection error', 'error');
        if (message.type !== 'notification' || typeof message.event_id !== 'string' || !message.data) return this.socket?.close(1003, 'invalid notification');
        const data = message.data;
        if (!Number.isInteger(data.reminder_id) || !Number.isInteger(data.task_id)) return this.socket?.close(1003, 'invalid notification');
        if (this.dedup.has(message.event_id)) return;
        this.dedup.set(message.event_id, true);
        setTimeout(() => this.dedup.delete(message.event_id), 10 * 60 * 1000);
        showToast(`Reminder: ${String(data.task || 'Task')} (#${data.reminder_id})`, 'success');
    }

    sendPing() {
        if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify({ type: 'ping' }));
    }
}

window.AuraNotifications = new AuraNotificationClient();
