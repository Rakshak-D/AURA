// Core dashboard load
document.addEventListener('DOMContentLoaded', async () => {
    loadTasks();
    loadSchedule();
    loadStats();
    connectWebSocket();
});

let ws;

function connectWebSocket() {
    ws = new WebSocket(`ws://localhost:8000/ws`);  // Add WS to FastAPI if needed
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'reminder') {
            showNotification(data.message);
        }
    };
}

function showNotification(msg) {
    const notif = document.getElementById('notifications');
    notif.textContent = msg;
    notif.classList.remove('hidden');
    setTimeout(() => notif.classList.add('hidden'), 5000);
}

async function loadTasks() {
    const res = await fetch('/api/tasks');
    const tasks = await res.json();
    const list = document.getElementById('tasks-list');
    list.innerHTML = tasks.map(t => `<li>${t.title} - ${t.completed ? 'Done' : 'Pending'}</li>`).join('');
}

async function loadSchedule() {
    const res = await fetch('/api/schedule');
    const sched = await res.json();
    document.getElementById('calendar').innerHTML = `<pre>${JSON.stringify(sched, null, 2)}</pre>`;
}

async function loadStats() {
    const ctx = document.getElementById('stats-chart').getContext('2d');
    const res = await fetch('/api/stats');
    const data = await res.json();
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Completed', 'Pending'],
            datasets: [{ data: [data.insights.completion_rate * 100, 100 - data.insights.completion_rate * 100] }]
        }
    });
}