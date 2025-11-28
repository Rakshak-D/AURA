// Chat Functionality
let currentChatContext = {};

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message) return;

    // Clear input
    input.value = '';
    input.style.height = 'auto';

    // Add User Message
    addMessage(message, 'user');

    // Show Loading
    const loadingId = addLoadingIndicator();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                context: currentChatContext
            })
        });

        const data = await response.json();

        // Remove Loading
        removeLoadingIndicator(loadingId);

        // Handle Widget Response
        if (data.type === 'widget') {
            renderWidget(data);
        } else if (data.response) {
            // Fallback to text or legacy task card
            if (data.action_taken === 'task_query' && data.data && data.data.tasks) {
                renderWidget({ type: 'widget', widget_type: 'task_list', data: { title: data.response, tasks: data.data.tasks } });
            } else {
                addMessage(data.response, 'assistant');
            }
        }

        // Handle Actions
        if (data.action_taken) {
            handleAction(data.action_taken, data.data);
        }

    } catch (error) {
        removeLoadingIndicator(loadingId);
        addMessage('I encountered an error. Please check your connection.', 'assistant', true);
        console.error('Chat Error:', error);
    }
}

function addMessage(text, sender, isError = false) {
    const history = document.getElementById('chat-history');
    const div = document.createElement('div');
    div.className = `message ${sender} ${isError ? 'error' : ''}`;

    // Use marked.js if available, otherwise fallback to text
    const content = typeof marked !== 'undefined' ? marked.parse(text) : text.replace(/\n/g, '<br>');

    div.innerHTML = `
        <div class="message-content">
            ${content}
        </div>
    `;

    history.appendChild(div);
    scrollToBottom();
    return div;
}

function renderWidget(widgetData) {
    const history = document.getElementById('chat-history');
    const div = document.createElement('div');
    div.className = 'message assistant';

    let content = '';

    if (widgetData.widget_type === 'task_list') {
        const tasks = widgetData.data.tasks || [];
        const tasksHtml = tasks.map(t => `
            <div class="task-card-widget">
                <input type="checkbox" ${t.completed ? 'checked' : ''} onclick="toggleTask(${t.id}, this.checked)">
                <div style="flex:1">
                    <div class="${t.completed ? 'completed' : ''}" style="font-weight:500">${t.title}</div>
                    <div style="font-size:0.8em; color:var(--text-secondary)">
                        ${t.due_date ? new Date(t.due_date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                        ${t.category ? `• ${t.category}` : ''}
                    </div>
                </div>
            </div>
        `).join('');

        content = `
            <div class="message-content">
                <p style="margin-bottom:10px">${widgetData.data.title || 'Here are your tasks:'}</p>
                ${tasksHtml}
            </div>
        `;
    } else if (widgetData.widget_type === 'calendar_snippet') {
        // Placeholder for calendar snippet
        content = `
            <div class="message-content">
                <p>📅 Calendar View</p>
                <div style="background:rgba(0,0,0,0.2); padding:10px; border-radius:8px;">
                    ${widgetData.data.events.map(e => `<div>${e.time} - ${e.title}</div>`).join('')}
                </div>
            </div>
        `;
    }

    div.innerHTML = content;
    history.appendChild(div);
    scrollToBottom();
}

function addLoadingIndicator() {
    const history = document.getElementById('chat-history');
    const id = 'loading-' + Date.now();
    const div = document.createElement('div');
    div.id = id;
    div.className = 'message assistant loading';
    div.innerHTML = `
        <div class="message-content">
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>
    `;
    history.appendChild(div);
    scrollToBottom();
    return id;
}

function removeLoadingIndicator(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function scrollToBottom() {
    const history = document.getElementById('chat-history');
    history.scrollTop = history.scrollHeight;
}

function handleChatInput(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
    e.target.style.height = 'auto';
    e.target.style.height = e.target.scrollHeight + 'px';
}

function setChatInput(text) {
    const input = document.getElementById('chat-input');
    input.value = text;
    input.focus();
}

function handleAction(action, data) {
    if (action === 'task_create' || action === 'task_update' || action === 'task_delete') {
        // Refresh tasks if on task view
        if (window.loadTasks) window.loadTasks();
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('chat-input');
    if (input) {
        input.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });
    }
});
