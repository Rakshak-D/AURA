const chatHistory = document.getElementById('chat-history');
const emptyState = document.getElementById('empty-state');

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const msg = input.value.trim();
    
    if (!msg) return;
    
    // UI Updates
    if (emptyState) emptyState.style.display = 'none';
    input.value = '';
    input.style.height = 'auto';
    
    appendMessage('user', msg);
    
    // Loading Indicator
    const loadingId = appendLoading();
    
    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: msg})
        });
        const data = await res.json();
        
        removeMessage(loadingId);
        appendMessage('aura', data.response);

        if (data.action_taken === 'task_created') {
            loadTasks(); // Refresh dashboard if task was made
            showNotification('Task scheduled successfully');
        }
        
    } catch (e) {
        removeMessage(loadingId);
        appendMessage('aura', "Sorry, I encountered an error.");
    }
}

function appendMessage(role, text) {
    const div = document.createElement('div');
    div.className = `flex w-full mb-6 ${role === 'user' ? 'justify-end' : 'justify-start'}`;
    
    const contentClass = role === 'user' 
        ? 'bg-[#282a2c] text-white rounded-2xl rounded-tr-none max-w-[80%]' 
        : 'text-gray-100 max-w-[90%] prose';

    const innerHTML = role === 'user'
        ? `<div class="px-5 py-3">${text}</div>`
        : `<div class="flex gap-4">
             <div class="w-8 h-8 bg-gradient-to-tr from-blue-500 to-purple-500 rounded-full flex-shrink-0 flex items-center justify-center">
                <i class="fa-solid fa-sparkles text-xs"></i>
             </div>
             <div class="mt-1">${marked.parse(text)}</div>
           </div>`;

    div.innerHTML = innerHTML;
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function appendLoading() {
    const id = 'loading-' + Date.now();
    const div = document.createElement('div');
    div.id = id;
    div.className = 'flex w-full mb-6 justify-start';
    div.innerHTML = `
        <div class="flex gap-4">
             <div class="w-8 h-8 bg-gradient-to-tr from-blue-500 to-purple-500 rounded-full flex items-center justify-center animate-pulse"></div>
             <div class="flex items-center gap-1">
                <div class="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></div>
                <div class="w-2 h-2 bg-gray-500 rounded-full animate-bounce delay-75"></div>
                <div class="w-2 h-2 bg-gray-500 rounded-full animate-bounce delay-150"></div>
             </div>
        </div>`;
    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    return id;
}

function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function handleChatKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}