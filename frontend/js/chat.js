// Chat Functionality
let currentChatContext = {};

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message) return;

    // Clear input and reset height to base size
    input.value = '';
    input.style.height = 'auto';

    // If welcome panel is visible, clear it before adding messages
    clearWelcomePanel();

    // Add User Message immediately
    addMessage(message, 'user');

    // Show typing indicator bubble
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

        // Remove typing indicator
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
                simulateStreaming(scheduleText, 'assistant');
            } else if (data.action_taken === 'task_query' && data.data && data.data.tasks) {
                renderWidget({ type: 'widget', widget_type: 'task_list', data: { title: data.response, tasks: data.data.tasks } });
            } else {
                simulateStreaming(data.response, 'assistant');
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

function renderMarkdown(text) {
    // Use marked.js if available for markdown support, otherwise fallback to text
    if (typeof marked !== 'undefined') {
        try {
            // Configure marked for safe rendering
            marked.setOptions({
                breaks: true,
                gfm: true,
                sanitize: false
            });
            return marked.parse(text);
        } catch (error) {
            console.error('Markdown parsing error:', error);
            // Fallback to plain text with line breaks
            return text.replace(/\n/g, '<br>');
        }
    }

    // Fallback: convert newlines to <br> and escape HTML
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>');
}

function addMessage(text, sender, isError = false) {
    const history = document.getElementById('chat-history');
    if (!history) {
        console.error('Chat history element not found');
        return null;
    }

    const div = document.createElement('div');
    div.className = `message ${sender} ${isError ? 'error' : ''} message-enter`;

    const content = renderMarkdown(text);

    div.innerHTML = `
        <div class="message-content markdown-body">
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

function simulateStreaming(fullText, sender) {
    const history = document.getElementById('chat-history');
    if (!history) return;

    const div = document.createElement('div');
    div.className = `message ${sender} message-enter`;

    const contentEl = document.createElement('div');
    contentEl.className = 'message-content markdown-body';
    div.appendChild(contentEl);

    history.appendChild(div);
    scrollToBottom();

    const tokens = fullText.split(/(\s+)/); // keep spaces
    let index = 0;

    const interval = setInterval(() => {
        if (index >= tokens.length) {
            clearInterval(interval);
            contentEl.innerHTML = renderMarkdown(fullText);
            scrollToBottom();
            return;
        }

        const partial = tokens.slice(0, index + 1).join('');
        contentEl.innerHTML = renderMarkdown(partial);
        index++;
        scrollToBottom();
    }, 25);
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

function renderWelcomeIfEmpty() {
    const history = document.getElementById('chat-history');
    if (!history) return;
    if (history.children.length > 0) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'chat-welcome';
    wrapper.innerHTML = `
        <div class="chat-welcome-title">Welcome to Aura</div>
        <div class="chat-welcome-subtitle">
            Your personal, context-aware assistant for planning, focus, and learning.
        </div>
        <div class="chat-suggestions">
            <button class="chat-suggestion-card" onclick="useSuggestion('Plan my day with my current tasks.')">
                <div class="chat-suggestion-title">Plan my day</div>
                <div class="chat-suggestion-body">Ask Aura to generate a focused schedule around your tasks.</div>
            </button>
            <button class="chat-suggestion-card" onclick="useSuggestion('Summarize what I did this week from my tasks.')">
                <div class="chat-suggestion-title">Weekly summary</div>
                <div class="chat-suggestion-body">Get a quick summary of your recent work and progress.</div>
            </button>
            <button class="chat-suggestion-card" onclick="useSuggestion('Help me break down a big project into smaller tasks.')">
                <div class="chat-suggestion-title">Break down a project</div>
                <div class="chat-suggestion-body">Turn a big goal into clear, actionable steps.</div>
            </button>
            <button class="chat-suggestion-card" onclick="useSuggestion('What can I do today to stay on track?')">
                <div class="chat-suggestion-title">Stay on track</div>
                <div class="chat-suggestion-body">Let Aura suggest what to focus on next.</div>
            </button>
        </div>
    `;
    history.appendChild(wrapper);
}

function clearWelcomePanel() {
    const history = document.getElementById('chat-history');
    if (!history) return;
    const welcome = history.querySelector('.chat-welcome');
    if (welcome) {
        welcome.remove();
    }
}

function useSuggestion(text) {
    const input = document.getElementById('chat-input');
    if (!input) return;
    input.value = text;
    input.focus();
    sendMessage();
}

async function clearChatHistory() {
    const history = document.getElementById('chat-history');
    if (!history) return;

    if (!confirm('Clear the current chat history?')) return;

    try {
        const response = await fetch(`${API_URL}/chat/history`, {
            method: 'DELETE'
        });
        // We ignore body shape; just clear UI on any 2xx
        if (!response.ok) {
            console.error('Failed to clear history', response.status);
        }
    } catch (err) {
        console.error('Error clearing history', err);
    }

    history.innerHTML = '';
    renderWelcomeIfEmpty();
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

    // Show welcome layout on initial load if no messages yet
    renderWelcomeIfEmpty();
});
