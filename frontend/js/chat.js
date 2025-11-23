// Chat Logic

function setChatInput(text) {
    const input = document.getElementById('chat-input');
    if (input) {
        input.value = text;
        input.focus();
        // Optional: Auto-send
        // sendMessage(); 
    }
}

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message) return;

    // Clear input
    input.value = '';

    // Add User Message
    addMessage('user', message);

    // Show Typing Indicator
    const typingId = showTypingIndicator();

    try {
        const response = await apiCall('/chat', 'POST', { message: message });

        // Remove Typing Indicator
        removeMessage(typingId);

        // Add Assistant Message
        if (response.response) {
            addMessage('assistant', response.response);
        }

        // Handle Actions
        if (response.action_taken) {
            handleAction(response.action_taken, response.data);
        }

    } catch (error) {
        console.error('Chat Error:', error);
        removeMessage(typingId);
        addMessage('assistant', 'I encountered an error. Please try again.');
    }
}

function addMessage(role, text) {
    const history = document.getElementById('chat-history');
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;

    // Format text (Markdown support could go here)
    // For now, simple text

    msgDiv.innerHTML = `
        <div class="message-content">
            ${formatMessageText(text)}
        </div>
    `;

    history.appendChild(msgDiv);
    history.scrollTop = history.scrollHeight;

    return msgDiv.id = 'msg-' + Date.now();
}

function formatMessageText(text) {
    // Basic formatting: newlines to <br>
    return text.replace(/\n/g, '<br>');
}

function showTypingIndicator() {
    const history = document.getElementById('chat-history');
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message assistant typing';
    msgDiv.id = 'typing-' + Date.now();

    msgDiv.innerHTML = `
        <div class="message-content">
            <div class="typing-dots">
                <span></span><span></span><span></span>
            </div>
        </div>
    `;

    history.appendChild(msgDiv);
    history.scrollTop = history.scrollHeight;
    return msgDiv.id;
}

function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function handleAction(action, data) {
    console.log('Action:', action, data);

    if (action === 'task_created' || action === 'task_completed') {
        // Refresh tasks if on task view
        if (typeof loadTasks === 'function') loadTasks();
        showToast(action === 'task_created' ? 'Task Created' : 'Task Completed', 'success');
    }
}

// Handle Enter key
function handleChatInput(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function handleChatFileUpload(event) {
    const file = event.target.files[0];
    if (file) {
        // Implement file upload logic here
        console.log('File selected:', file.name);
        showToast(`Selected: ${file.name}`, 'info');
    }
}
