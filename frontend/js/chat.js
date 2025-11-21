// Chat functionality
const chatInput = document.getElementById('chat-input');
const chatHistory = document.getElementById('chat-history');
const sendBtn = document.getElementById('send-btn');

function handleChatInput(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
    
    // Auto-expand textarea
    e.target.style.height = 'auto';
    e.target.style.height = e.target.scrollHeight + 'px';
}

async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;
    
    // Hide empty state
    const emptyState = document.getElementById('empty-state');
    if (emptyState) {
        emptyState.style.display = 'none';
    }
    
    // Clear input
    chatInput.value = '';
    chatInput.style.height = 'auto';
    
    // Add user message
    addMessage('user', text);
    
    // Show loading
    const loadingId = 'loading-' + Date.now();
    addMessage('ai', '<div class="typing-indicator"><span></span><span></span><span></span></div>', loadingId);
    
    try {
        // Send to API
        const response = await apiCall('/chat', 'POST', { message: text });
        
        // Remove loading
        const loadingMsg = document.getElementById(loadingId);
        if (loadingMsg) {
            loadingMsg.remove();
        }
        
        // Add AI response
        addMessage('ai', response.response);
        
        // Add suggestions if available
        if (response.suggestions && response.suggestions.length > 0) {
            addSuggestions(response.suggestions);
        }
        
        // Handle actions
        if (response.action_taken === 'task_created' || response.action_taken === 'task_completed') {
            // Refresh tasks if in tasks view
            if (currentView === 'tasks') {
                loadTasks();
            }
        }
        
    } catch (error) {
        // Remove loading
        const loadingMsg = document.getElementById(loadingId);
        if (loadingMsg) {
            loadingMsg.remove();
        }
        
        addMessage('ai', '❌ Sorry, I encountered an error. Please try again.');
        console.error('Chat error:', error);
    }
    
    // Scroll to bottom
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function addMessage(role, content, id = null) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}-message`;
    if (id) msgDiv.id = id;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'user' ? '👤' : '🤖';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = content;
    
    msgDiv.appendChild(avatar);
    msgDiv.appendChild(contentDiv);
    
    chatHistory.appendChild(msgDiv);
    
    // Scroll to bottom
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function addSuggestions(suggestions) {
    const suggestionsDiv = document.createElement('div');
    suggestionsDiv.className = 'message-suggestions';
    
    suggestions.forEach(suggestion => {
        const chip = document.createElement('button');
        chip.className = 'suggestion-chip';
        chip.textContent = suggestion;
        chip.onclick = () => fillInput(suggestion);
        suggestionsDiv.appendChild(chip);
    });
    
    chatHistory.appendChild(suggestionsDiv);
}
