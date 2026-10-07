// Chat Functionality
let currentChatContext = {};
let chatRequestActive = false;

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message) return;
    if (chatRequestActive) {
        showToast('Please wait for the current response to finish.', 'error');
        return;
    }
    chatRequestActive = true;

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
        const data = await apiJson(`${API_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                context: currentChatContext
            })
        });

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
        addMessage('I encountered an error. Please check your connection.', 'assistant', true);
        showToast(error.message || 'Chat request failed', 'error');
    } finally {
        removeLoadingIndicator(loadingId);
        chatRequestActive = false;
    }
}

function renderMarkdown(text) {
    // Model output is untrusted. Plain text is the deliberate safe format.
    return text == null ? '' : String(text);
}

function addMessage(text, sender, isError = false) {
    const history = document.getElementById('chat-history');
    if (!history) {
        console.error('Chat history element not found');
        return null;
    }

    const div = document.createElement('div');
    div.className = `message ${sender} ${isError ? 'error' : ''} message-enter`;

    const contentEl = AuraSafe.element('div', 'message-content markdown-body');
    AuraSafe.text(contentEl, renderMarkdown(text));
    div.appendChild(contentEl);

    history.appendChild(div);

    // Auto-scroll with smooth behavior
    setTimeout(() => scrollToBottom(), 50);

    return div;
}

function renderWidget(widgetData) {
    const history = document.getElementById('chat-history');
    const div = document.createElement('div');
    div.className = 'message assistant';

    if (widgetData.widget_type === 'task_list') {
        const tasks = widgetData.data.tasks || [];
        const content = AuraSafe.element('div', 'message-content');
        content.appendChild(AuraSafe.element('p', null, widgetData.data.title || 'Here are your tasks:'));
        tasks.forEach((task) => {
            const card = AuraSafe.element('div', 'task-card-widget');
            const checkbox = AuraSafe.element('input');
            checkbox.type = 'checkbox';
            checkbox.checked = Boolean(task.completed);
            checkbox.addEventListener('change', () => toggleComplete(task.id, !checkbox.checked));
            const body = AuraSafe.element('div');
            body.style.flex = '1';
            const title = AuraSafe.element('div', task.completed ? 'completed' : '');
            title.style.fontWeight = '500';
            AuraSafe.text(title, task.title);
            const meta = AuraSafe.element('div');
            meta.style.cssText = 'font-size:0.8em;color:var(--text-secondary)';
            const time = task.due_date ? new Date(task.due_date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
            AuraSafe.text(meta, `${time}${task.category ? ` • ${task.category}` : ''}`);
            body.append(title, meta);
            card.append(checkbox, body);
            content.appendChild(card);
        });
        div.appendChild(content);
    } else if (widgetData.widget_type === 'calendar_snippet') {
        const content = AuraSafe.element('div', 'message-content');
        content.appendChild(AuraSafe.element('p', null, '📅 Calendar View'));
        const events = AuraSafe.element('div');
        events.style.cssText = 'background:rgba(0,0,0,0.2);padding:10px;border-radius:8px';
        (widgetData.data.events || []).forEach((event) => {
            events.appendChild(AuraSafe.element('div', null, `${event.time || ''} - ${event.title || ''}`));
        });
        content.appendChild(events);
        div.appendChild(content);
    }
    history.appendChild(div);
    scrollToBottom();
}

function addLoadingIndicator() {
    const history = document.getElementById('chat-history');
    const id = 'loading-' + Date.now();
    const div = document.createElement('div');
    div.id = id;
    div.className = 'message assistant loading';
    const content = AuraSafe.element('div', 'message-content');
    const indicator = AuraSafe.element('div', 'typing-indicator');
    indicator.append(
        AuraSafe.element('div', 'typing-dot'),
        AuraSafe.element('div', 'typing-dot'),
        AuraSafe.element('div', 'typing-dot')
    );
    content.appendChild(indicator);
    div.appendChild(content);
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

function renderWelcomeIfEmpty() {
    const history = document.getElementById('chat-history');
    if (!history) return;
    if (history.children.length > 0) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'chat-welcome';
    wrapper.appendChild(AuraSafe.element('div', 'chat-welcome-title', 'Welcome to Aura'));
    wrapper.appendChild(AuraSafe.element('div', 'chat-welcome-subtitle', 'Your personal, context-aware assistant for planning, focus, and learning.'));
    const suggestions = AuraSafe.element('div', 'chat-suggestions');
    [
        ['Plan my day', 'Plan my day with my current tasks.'],
        ['Weekly summary', 'Summarize what I did this week from my tasks.'],
        ['Break down a project', 'Help me break down a big project into smaller tasks.'],
        ['Stay on track', 'What can I do today to stay on track?']
    ].forEach(([title, prompt]) => {
        const button = AuraSafe.element('button', 'chat-suggestion-card');
        button.type = 'button';
        button.append(AuraSafe.element('div', 'chat-suggestion-title', title), AuraSafe.element('div', 'chat-suggestion-body', prompt));
        button.addEventListener('click', () => useSuggestion(prompt));
        suggestions.appendChild(button);
    });
    wrapper.appendChild(suggestions);
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
        const response = await apiFetch(`${API_URL}/chat/history`, {
            method: 'DELETE'
        });
        if (!response.ok) {
            throw new Error('Failed to clear chat history');
        }
        AuraSafe.clear(history);
        renderWelcomeIfEmpty();
    } catch (err) {
        showToast(err.message || 'Failed to clear chat history', 'error');
    }
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
