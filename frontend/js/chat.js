// Chat functionality with improved message rendering

function handleChatInput(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }

    // Auto-resize
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
}

async function sendMessage() {
    const chatInput = document.getElementById('chat-input');
    const chatHistory = document.getElementById('chat-history');

    if (!chatInput || !chatHistory) return;

    const text = chatInput.value.trim();
    if (!text) return;

    // Hide welcome section
    const welcomeSection = chatHistory.querySelector('.welcome-section');
    if (welcomeSection) {
        welcomeSection.style.display = 'none';
    }

    chatInput.value = '';
    chatInput.style.height = 'auto';

    addMessage('user', text);

    // Add typing indicator manually to avoid escaping issues
    const loadingId = 'loading-' + Date.now();
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message assistant';
    loadingDiv.id = loadingId;
    loadingDiv.innerHTML = `
        <div class="avatar">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="url(#grad1)" stroke-width="2"/>
                <path d="M12 8v8m-4-4h8" stroke="url(#grad1)" stroke-width="2" stroke-linecap="round"/>
                <defs>
                    <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" style="stop-color:#667eea;stop-opacity:1" />
                        <stop offset="100%" style="stop-color:#764ba2;stop-opacity:1" />
                    </linearGradient>
                </defs>
            </svg>
        </div>
        <div class="message-content">
            <div class="typing-indicator"><span></span><span></span><span></span></div>
        </div>
    `;
    chatHistory.appendChild(loadingDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    try {
        const userName = localStorage.getItem('aura-username') || 'Rakshak';
        const response = await apiCall('/chat', 'POST', {
            message: text,
            context: { user_name: userName }
        });

        const loadingMsg = document.getElementById(loadingId);
        if (loadingMsg) {
            loadingMsg.remove();
        }

        addMessage('assistant', response.response);

        if (response.action_taken === 'task_created' || response.action_taken === 'task_completed') {
            if (currentView === 'tasks') {
                loadTasks();
            }
        }

    } catch (error) {
        const loadingMsg = document.getElementById(loadingId);
        if (loadingMsg) {
            loadingMsg.remove();
        }

        addMessage('assistant', '❌ Sorry, I encountered an error. Please try again.');
        console.error('Chat error:', error);
    }
}

function addMessage(role, content, id = null) {
    const chatHistory = document.getElementById('chat-history');
    if (!chatHistory) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    if (id) messageDiv.id = id;

    // Create avatar
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'avatar';

    if (role === 'user') {
        const userName = localStorage.getItem('aura-username') || 'Rakshak';
        avatarDiv.textContent = userName.charAt(0).toUpperCase();
    } else {
        avatarDiv.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="url(#grad1)" stroke-width="2"/>
            <path d="M12 8v8m-4-4h8" stroke="url(#grad1)" stroke-width="2" stroke-linecap="round"/>
            <defs>
                <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style="stop-color:#667eea;stop-opacity:1" />
                    <stop offset="100%" style="stop-color:#764ba2;stop-opacity:1" />
                </linearGradient>
            </defs>
        </svg>`;
    }

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    // Parse Markdown if it's from assistant
    if (role === 'assistant') {
        if (typeof marked !== 'undefined') {
            contentDiv.innerHTML = marked.parse(content);
            // Apply syntax highlighting
            if (typeof hljs !== 'undefined') {
                contentDiv.querySelectorAll('pre code').forEach((block) => {
                    hljs.highlightElement(block);
                });
            }
        } else {
            contentDiv.textContent = content; // Fallback
        }
    } else {
        contentDiv.textContent = content;
    }

    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);

    chatHistory.appendChild(messageDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

// Handle file upload from chat
async function handleChatFileUpload(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    for (let file of files) {
        const formData = new FormData();
        formData.append('file', file);

        try {
            showToast(`Uploading ${file.name}...`, 'info');

            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('Upload failed');
            }

            showToast(`✅ ${file.name} uploaded successfully!`);
            addMessage('assistant', `I've learned from "${file.name}". You can now ask me questions about it!`);

        } catch (error) {
            console.error('Upload error:', error);
            showToast(`Failed to upload ${file.name}`, 'error');
        }
    }

    // Reset file input
    event.target.value = '';
}
