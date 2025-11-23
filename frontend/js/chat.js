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

        // Handle Response
        if (data.response) {
            // Check for structured data to render cards
            if (data.action_taken === 'task_query' && data.data && data.data.tasks) {
                addTaskCard(data.response, data.data.tasks);
            } else {
                addMessage(data.response, 'assistant');
            }
        }

        // Handle Actions
        if (data.action_taken) {
            handleAction(data.action_taken, data.data);
        }

        // Update Suggestions
        if (data.suggestions) {
            updateSuggestions(data.suggestions);
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

    // Convert markdown-like links to HTML
    // Simple regex for [text](url)
    const formattedText = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
        .replace(/\n/g, '<br>');

    div.innerHTML = `
        <div class="message-content">
            ${formattedText}
        </div>
    `;

    history.appendChild(div);
    scrollToBottom();
    return div;
}

function addTaskCard(title, tasks) {
    const history = document.getElementById('chat-history');
    const div = document.createElement('div');
    div.className = 'message assistant';

    let tasksHtml = tasks.map(t => `
        <div class="task-card-item">
            <input type="checkbox" ${t.completed ? 'checked' : ''} onclick="toggleTask(${t.id}, this.checked)">
            <span class="${t.completed ? 'completed' : ''}">${t.title}</span>
            <span class="task-time">${t.due_date ? new Date(t.due_date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}</span>
        </div>
    `).join('');

    div.innerHTML = `
        <div class="message-content task-card">
            <p>${title}</p>
            <div class="task-list-card">
                ${tasksHtml}
            </div>
        </div>
    `;

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
                <span></span><span></span><span></span>
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
    // Auto-resize
    e.target.style.height = 'auto';
    e.target.style.height = e.target.scrollHeight + 'px';
}

function setChatInput(text) {
    const input = document.getElementById('chat-input');
    input.value = text;
    input.focus();
}

function updateSuggestions(suggestions) {
    // Optional: Update suggestion chips dynamically
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
