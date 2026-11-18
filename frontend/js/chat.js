// Chat Functionality
let chatRequestActive = false;

// A1-G authenticated SSE client. Provider output is always assigned via textContent.
let activeChatController = null;
let chatGeneration = 0;
let chatAutoFollow = true;

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input?.value.trim();
    if (!message || chatRequestActive) return;

    chatRequestActive = true;
    const generation = ++chatGeneration;
    const controller = new AbortController();
    activeChatController = controller;
    setChatBusy(true);
    input.value = '';
    input.style.height = 'auto';
    clearWelcomePanel();
    chatAutoFollow = true;
    addMessage(message, 'user');

    const responseBubble = createStreamingBubble();
    const content = responseBubble.querySelector('.streamed-content');
    const sourceBadge = responseBubble.querySelector('.message-source');
    let requestId = null;
    let outputBytes = 0;
    let complete = false;
    let failed = false;

    try {
        setChatStatus('Connecting…');
        const response = await apiFetch(`${API_URL}/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
            signal: controller.signal,
        });
        if (!response.ok || !response.body) {
            throw new Error('Chat could not connect to the selected model. Check Settings → Models and try again.');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        const encoder = new TextEncoder();
        let buffer = '';
        const byteLength = value => encoder.encode(value).byteLength;
        while (generation === chatGeneration) {
            const { value, done } = await reader.read();
            if (done) break;
            const decoded = decoder.decode(value, { stream: true });
            const pending = buffer + decoded;
            let offset = 0;
            let boundary;
            while ((boundary = pending.indexOf('\n\n', offset)) >= 0) {
                const eventText = pending.slice(offset, boundary);
                if (byteLength(eventText) > 32_768) {
                    throw new Error('The Chat stream exceeded its event limit.');
                }
                const parsed = parseChatEvent(eventText);
                offset = boundary + 2;
                if (!parsed) continue;
                const { event, payload } = parsed;
                if (event === 'started' && typeof payload.request_id !== 'string') {
                    throw new Error('The Chat stream returned an invalid request identity.');
                }
                if (event !== 'started' && !requestId) {
                    throw new Error('The Chat stream did not start correctly.');
                }
                if (requestId && payload.request_id !== requestId) continue;
                if (event === 'started') {
                    requestId = payload.request_id;
                    if (payload.model_id && typeof payload.model_id === 'string') {
                        const locality = payload.locality === 'local' ? 'Local' : providerDisplayName(payload.provider_type);
                        sourceBadge.textContent = locality;
                        sourceBadge.hidden = false;
                        sourceBadge.setAttribute('aria-label', `Response source: ${locality}`);
                        updateChatModelIndicator(payload.model_id, locality);
                    }
                    setChatStatus(payload.model_id ? 'Generating response…' : 'Working…');
                } else if (event === 'text_delta') {
                    if (typeof payload.delta !== 'string') throw new Error('The Chat stream returned an invalid text event.');
                    outputBytes += new TextEncoder().encode(payload.delta).length;
                    if (outputBytes > 1_048_576) throw new Error('The Chat response exceeded the display limit.');
                    content.textContent += payload.delta;
                    responseBubble.classList.toggle('has-content', Boolean(content.textContent));
                    if (chatAutoFollow) scrollToBottom(false);
                } else if (event === 'completed') {
                    complete = true;
                    failed = false;
                    responseBubble.classList.remove('incomplete');
                    setChatStatus('Response complete');
                    if (payload.action_taken) handleAction(payload.action_taken, payload.data || {});
                } else if (event === 'failed') {
                    failed = true;
                    const safeMessage = typeof payload.message === 'string'
                        ? payload.message
                        : 'The selected model could not complete this request.';
                    if (!content.textContent) content.textContent = safeMessage;
                    if (payload.incomplete) markStreamIncomplete(responseBubble, true);
                    else responseBubble.classList.add('error');
                    setChatStatus('Response unavailable');
                } else if (event === 'cancelled') {
                    failed = true;
                    markStreamStopped(responseBubble);
                    setChatStatus('Generation stopped');
                }
            }
            buffer = pending.slice(offset);
            if (byteLength(buffer) > 32_768) {
                throw new Error('The Chat stream exceeded its event limit.');
            }
        }

        if (!complete && !failed && generation === chatGeneration && !controller.signal.aborted) {
            markStreamIncomplete(responseBubble, Boolean(content.textContent), 'The response ended before the model completed it.');
            setChatStatus('Response interrupted');
        }
    } catch (error) {
        if (generation === chatGeneration) {
            if (controller.signal.aborted) {
                markStreamStopped(responseBubble);
                setChatStatus('Generation stopped');
            } else {
                if (!content.textContent) content.textContent = error.message || 'The selected model could not complete this request.';
                responseBubble.classList.add('error');
                setChatStatus('Response unavailable');
            }
        }
    } finally {
        if (generation === chatGeneration) {
            chatRequestActive = false;
            activeChatController = null;
            setChatBusy(false);
            if (chatAutoFollow) scrollToBottom(false);
        }
    }
}

function stopGeneration() {
    if (activeChatController) activeChatController.abort();
}

function setChatBusy(busy) {
    const send = document.querySelector('[data-action="send-message"]');
    const stop = document.querySelector('[data-action="stop-generation"]');
    if (send) send.hidden = busy;
    if (stop) stop.hidden = !busy;
    if (stop) stop.disabled = !busy;
    const input = document.getElementById('chat-input');
    if (input) input.setAttribute('aria-busy', String(busy));
}

function setChatStatus(value) {
    const status = document.getElementById('chat-status');
    if (status) status.textContent = value;
}

function providerDisplayName(providerType) {
    if (providerType === 'ollama') return 'Ollama';
    if (providerType === 'openai_compatible') return 'OpenAI-compatible';
    return 'Cloud provider';
}

function updateChatModelIndicator(modelId, locality) {
    const indicator = document.getElementById('chat-model-indicator');
    if (indicator) indicator.textContent = `${locality} · ${modelId}`;
}

function createStreamingBubble() {
    const bubble = document.createElement('div');
    bubble.className = 'message assistant streaming-message';
    const badge = AuraSafe.element('span', 'message-source');
    badge.hidden = true;
    const content = AuraSafe.element('div', 'message-content streamed-content');
    const status = AuraSafe.element('span', 'message-completion-status');
    bubble.append(badge, content, status);
    document.getElementById('chat-history').appendChild(bubble);
    if (chatAutoFollow) scrollToBottom(false);
    return bubble;
}

function markStreamIncomplete(bubble, partial, message = 'Incomplete response') {
    bubble.classList.add('incomplete');
    const status = bubble.querySelector('.message-completion-status');
    if (status) status.textContent = partial ? message : '';
}

function markStreamStopped(bubble) {
    bubble.classList.add('stopped');
    const status = bubble.querySelector('.message-completion-status');
    if (status) status.textContent = 'Stopped';
}

function parseChatEvent(rawEvent) {
    let eventName = '';
    const dataLines = [];
    for (const line of rawEvent.split(/\r?\n/)) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
    }
    if (!eventName || !dataLines.length) return null;
    try {
        const payload = JSON.parse(dataLines.join('\n'));
        if (!payload || typeof payload !== 'object') throw new Error('invalid event');
        return { event: eventName, payload };
    } catch (_error) {
        throw new Error('The Chat stream returned an invalid event.');
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

    if (chatAutoFollow) scrollToBottom(false);

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

function scrollToBottom(force = false) {
    const history = document.getElementById('chat-history');
    if (!history) return;
    if (!force && !chatAutoFollow) return;
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
    const welcome = history.querySelector('.chat-welcome, .welcome-panel');
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
    const history = document.getElementById('chat-history');
    if (history) {
        history.addEventListener('scroll', () => {
            const remaining = history.scrollHeight - history.clientHeight - history.scrollTop;
            chatAutoFollow = remaining <= 80;
        }, { passive: true });
    }
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
