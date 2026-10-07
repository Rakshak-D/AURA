// Main Application Logic

// Global Configuration
const API_URL = '/api';
const API_REQUEST_TIMEOUT_MS = 15000;

// Global State
document.addEventListener('DOMContentLoaded', () => {
    // Initialize Lucide Icons
    lucide.createIcons();

    // Default View
    switchView('chat');

    // Initialize Voice
    setupVoice();
    ensureAuthenticated();
    if (getAuthToken()) AuraNotifications.start();
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
    const controller = options.signal ? null : new AbortController();
    const timeout = controller ? setTimeout(() => controller.abort(), API_REQUEST_TIMEOUT_MS) : null;
    try {
        const response = await fetch(url, { ...options, headers, ...(controller ? { signal: controller.signal } : {}) });
        if (response.status === 401) {
            clearAuthToken();
            AuraNotifications.stop();
            showAuthPanel();
        }
        return response;
    } finally {
        if (timeout) clearTimeout(timeout);
    }
}

async function apiJson(url, options = {}) {
    const response = await apiFetch(url, options);
    const contentType = response.headers.get('content-type') || '';
    let body = null;
    if (contentType.includes('application/json')) {
        body = await response.json().catch(() => null);
        if (response.ok && response.status !== 204 && body === null) {
            throw new Error('Invalid JSON response');
        }
    } else if (!response.ok) {
        await response.text().catch(() => '');
    } else if (response.status !== 204) {
        throw new Error('Invalid JSON response');
    }
    if (!response.ok) {
        const detail = body?.detail || body?.message || body?.error?.message || `Request failed (${response.status})`;
        throw new Error(String(detail));
    }
    if (body && body.success === false) {
        throw new Error(String(body.message || body.error?.message || 'Request failed'));
    }
    return body;
}

function showAuthPanel() {
    const panel = document.getElementById('aura-auth-panel');
    if (panel) {
        panel.hidden = false;
        panel.style.display = 'grid';
    }
}

function hideAuthPanel() {
    const panel = document.getElementById('aura-auth-panel');
    if (panel) {
        panel.hidden = true;
        panel.style.display = 'none';
    }
}

async function authenticate(action = 'login') {
    try {
        const identifier = document.getElementById('aura-auth-identifier').value;
        const password = document.getElementById('aura-auth-password').value;
        const data = await apiJson(`${API_URL}/auth/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identifier, password })
        });
        if (action === 'register') return authenticate('login');
        if (!data?.access_token) throw new Error('Authentication response was invalid');
        sessionStorage.setItem(AUTH_TOKEN_KEY, data.access_token);
        hideAuthPanel();
        AuraNotifications.start();
        if (typeof loadSettings === 'function') loadSettings();
        if (typeof loadTasks === 'function') loadTasks();
        if (typeof loadUploadedFiles === 'function') loadUploadedFiles();
        showToast('Signed in');
    } catch (error) {
        showToast(error.message || 'Authentication failed', 'error');
    }
}

function logout() {
    clearAuthToken();
    AuraNotifications.stop();
    stopVoiceInput();
    showAuthPanel();
}

function ensureAuthenticated() {
    if (document.getElementById('aura-auth-panel')) return;
    const panel = document.createElement('section');
    panel.id = 'aura-auth-panel';
    panel.hidden = Boolean(getAuthToken());
    panel.style.cssText = `position:fixed;inset:0;background:rgba(10,15,30,.96);z-index:2000;display:${getAuthToken() ? 'none' : 'grid'};place-items:center;color:white`;
    const form = document.createElement('form');
    form.style.cssText = 'display:grid;gap:12px;width:min(360px,90vw);padding:24px;background:#172033;border-radius:12px';
    const title = AuraSafe.element('h2', null, 'Sign in to AURA');
    const identifier = AuraSafe.element('input');
    identifier.id = 'aura-auth-identifier';
    identifier.required = true;
    identifier.minLength = 3;
    identifier.placeholder = 'Username or email';
    const password = AuraSafe.element('input');
    password.id = 'aura-auth-password';
    password.required = true;
    password.minLength = 8;
    password.type = 'password';
    password.placeholder = 'Password';
    const loginButton = AuraSafe.element('button', null, 'Sign in');
    loginButton.type = 'submit';
    const registerButton = AuraSafe.element('button', null, 'Create account');
    registerButton.type = 'button';
    form.append(title, identifier, password, loginButton, registerButton);
    form.addEventListener('submit', (event) => {
        event.preventDefault();
        authenticate('login');
    });
    registerButton.addEventListener('click', () => authenticate('register'));
    panel.appendChild(form);
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
    if (viewId === 'insights' && typeof loadAnalytics === 'function') {
        loadAnalytics();
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
