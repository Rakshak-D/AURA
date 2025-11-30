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
        const response = await fetch(`${API_URL}/chat`, {
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
            // Handle schedule queries with formatted lists
            if (data.action_taken === 'query_schedule' && data.data && data.data.events) {
                // Format schedule as markdown list for better display
                let scheduleText = data.response;
                if (data.data.events && data.data.events.length > 0) {
                    scheduleText += '\n\n**Events:**\n';
                    data.data.events.forEach((event, idx) => {
                        const start = new Date(event.start);
                        const timeStr = start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                        scheduleText += `${idx + 1}. ${event.title} - ${timeStr}\n`;
                    });
                }
                addMessage(scheduleText, 'assistant');
            } else if (data.action_taken === 'task_query' && data.data && data.data.tasks) {
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
    if (!history) {
        console.error('Chat history element not found');
        return null;
    }
    
    const div = document.createElement('div');
    div.className = `message ${sender} ${isError ? 'error' : ''}`;

    // Use marked.js if available for markdown support, otherwise fallback to text
    let content = text;
    if (typeof marked !== 'undefined') {
        try {
            // Configure marked for safe rendering
            marked.setOptions({
                breaks: true,
                gfm: true,
                sanitize: false
            });
            content = marked.parse(text);
        } catch (error) {
            console.error('Markdown parsing error:', error);
            // Fallback to plain text with line breaks
            content = text.replace(/\n/g, '<br>');
        }
    } else {
        // Fallback: convert newlines to <br> and escape HTML
        content = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br>');
    }

    div.innerHTML = `
        <div class="message-content">
            ${content}
        </div>
    `;

    history.appendChild(div);
    
    // Auto-scroll with smooth behavior
    setTimeout(() => scrollToBottom(), 50);
    
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
                <input type="checkbox" ${t.completed ? 'checked' : ''} onclick="toggleComplete(${t.id}, !this.checked)">
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
    if (!history) return;
    
    // Smooth scroll to bottom
    history.scrollTo({
        top: history.scrollHeight,
        behavior: 'smooth'
    });
    
    // Fallback for browsers that don't support smooth scroll
    if (history.scrollTop !== history.scrollHeight) {
        history.scrollTop = history.scrollHeight;
    }
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
        // Auto-resize textarea
        input.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });
        
        // Handle Enter key to send message
        input.addEventListener('keydown', handleChatInput);
    }
});
