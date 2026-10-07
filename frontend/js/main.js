// Main Application Logic

// Global Configuration
const API_URL = '/api';

// Global State
let isVoiceActive = false;
let recognition = null;

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Lucide Icons
    lucide.createIcons();

    // Default View
    switchView('chat');

    // Initialize Voice
    setupVoice();
    ensureAuthenticated();
});

const AUTH_TOKEN_KEY = 'aura_access_token';

function getAuthToken() {
    return sessionStorage.getItem(AUTH_TOKEN_KEY);
}

function clearAuthToken() {
    sessionStorage.removeItem(AUTH_TOKEN_KEY);
}

async function apiFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});
    const token = getAuthToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401) {
        clearAuthToken();
        showAuthPanel();
    }
    return response;
}

function showAuthPanel() {
    const panel = document.getElementById('aura-auth-panel');
    if (panel) panel.hidden = false;
}

function hideAuthPanel() {
    const panel = document.getElementById('aura-auth-panel');
    if (panel) panel.hidden = true;
}

async function authenticate(action = 'login') {
    const identifier = document.getElementById('aura-auth-identifier').value;
    const password = document.getElementById('aura-auth-password').value;
    const response = await fetch(`${API_URL}/auth/${action}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier, password })
    });
    const data = await response.json();
    if (!response.ok) return showToast(data.detail || 'Authentication failed', 'error');
    if (action === 'register') {
        return authenticate('login');
    }
    sessionStorage.setItem(AUTH_TOKEN_KEY, data.access_token);
    hideAuthPanel();
    showToast('Signed in');
}

function logout() {
    clearAuthToken();
    showAuthPanel();
}

function ensureAuthenticated() {
    if (document.getElementById('aura-auth-panel')) return;
    const panel = document.createElement('section');
    panel.id = 'aura-auth-panel';
    panel.hidden = Boolean(getAuthToken());
    panel.style.cssText = 'position:fixed;inset:0;background:rgba(10,15,30,.96);z-index:2000;display:grid;place-items:center;color:white';
    panel.innerHTML = `<form style="display:grid;gap:12px;width:min(360px,90vw);padding:24px;background:#172033;border-radius:12px" onsubmit="event.preventDefault(); authenticate('login')">
        <h2>Sign in to AURA</h2><input id="aura-auth-identifier" required minlength="3" placeholder="Username or email">
        <input id="aura-auth-password" required minlength="8" type="password" placeholder="Password">
        <button type="submit">Sign in</button><button type="button" onclick="authenticate('register')">Create account</button></form>`;
    document.body.appendChild(panel);
}

// View Switching
function switchView(viewId) {
    // Hide all views
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));

    // Show selected view
    const target = document.getElementById(`view-${viewId}`);
    if (target) target.classList.add('active');

    // Update Sidebar Active State
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    // Find button that calls this view
    const btn = document.querySelector(`button[onclick="switchView('${viewId}')"]`);
    if (btn) btn.classList.add('active');

    // Close sidebar on mobile after selection
    if (window.innerWidth <= 768) {
        document.getElementById('sidebar').classList.remove('open');
    }

    // Trigger view-specific initialization
    if (viewId === 'calendar') {
        // Wait a bit for DOM to be ready, then render
        setTimeout(() => {
            console.log('Switching to calendar view, initializing...');
            // Force update date header
            if (typeof updateDateHeader === 'function') {
                updateDateHeader();
            }
            // Render calendar
            if (typeof renderCalendar === 'function') {
                console.log('Calling renderCalendar()');
                renderCalendar();
            } else {
                console.warn('renderCalendar function not found');
            }
        }, 200);
    } else if (viewId === 'tasks' && typeof loadTasks === 'function') {
        setTimeout(() => loadTasks(), 100);
    }
}

// Sidebar Toggle (Mobile)
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('open');
}

// Toast Notifications
function showToast(message, type = 'success') {
    // Create toast element
    const toast = document.createElement('div');
    toast.style.position = 'fixed';
    toast.style.bottom = '20px';
    toast.style.right = '20px';
    toast.style.padding = '1rem 1.5rem';
    toast.style.borderRadius = '8px';
    toast.style.color = 'white';
    toast.style.fontWeight = '500';
    toast.style.zIndex = '1000';
    toast.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
    toast.style.animation = 'slideIn 0.3s ease';

    if (type === 'error') {
        toast.style.background = '#EF4444';
    } else {
        toast.style.background = '#10B981';
    }

    toast.textContent = message;
    document.body.appendChild(toast);

    // Remove after 3s
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Voice Recognition
function setupVoice() {
    if ('webkitSpeechRecognition' in window) {
        recognition = new webkitSpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;

        recognition.onresult = (event) => {
            const text = event.results[0][0].transcript;
            document.getElementById('chat-input').value = text;
            sendMessage(); // Auto-send
        };

        recognition.onend = () => {
            isVoiceActive = false;
            updateVoiceIcon();
        };

        recognition.onerror = (event) => {
            console.error("Voice error:", event.error);
            isVoiceActive = false;
            updateVoiceIcon();
            showToast("Voice recognition error", "error");
        };
    } else {
        console.warn("Web Speech API not supported");
    }
}

function toggleVoice() {
    if (!recognition) return showToast("Voice not supported", "error");

    if (isVoiceActive) {
        recognition.stop();
    } else {
        recognition.start();
        isVoiceActive = true;
    }
    updateVoiceIcon();
}

function updateVoiceIcon() {
    const btn = document.querySelector('.icon-btn i[data-lucide="mic"]');
    if (btn) {
        if (isVoiceActive) {
            btn.parentElement.style.color = '#EF4444';
            btn.parentElement.classList.add('pulse');
        } else {
            btn.parentElement.style.color = '';
            btn.parentElement.classList.remove('pulse');
        }
    }
}

// Global API Call Helper
async function apiCall(endpoint, method = 'GET', body = null) {
    try {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };
        if (body) options.body = JSON.stringify(body);

        const response = await apiFetch(`${API_URL}${endpoint}`, options);
        return await response.json();
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        showToast("Connection error", "error");
        return null;
    }
}
