// Main Application Logic

// Global Configuration
const API_URL = '/api';
const API_REQUEST_TIMEOUT_MS = 15000;
let lucideWarningShown = false;

function refreshLucideIcons() {
    if (typeof window.lucide?.createIcons !== 'function') {
        if (!lucideWarningShown) {
            console.warn('Lucide is unavailable; the application will continue without icon rendering.');
            lucideWarningShown = true;
        }
        return false;
    }

    try {
        window.lucide.createIcons();
        return true;
    } catch (error) {
        if (!lucideWarningShown) {
            console.warn('Lucide icon rendering failed; the application will continue.', error);
            lucideWarningShown = true;
        }
        return false;
    }
}

// Global State
document.addEventListener('DOMContentLoaded', () => {
    refreshLucideIcons();

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
    if (panel) panel.hidden = false;
}

function hideAuthPanel() {
    const panel = document.getElementById('aura-auth-panel');
    if (panel) panel.hidden = true;
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
    panel.className = 'aura-auth-panel';
    panel.hidden = Boolean(getAuthToken());
    const form = document.createElement('form');
    form.className = 'aura-auth-form';
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
    const btn = document.querySelector(`button[data-view="${CSS.escape(viewId)}"]`);
    if (btn) btn.classList.add('active');

    // Close sidebar on mobile after selection
    if (window.innerWidth <= 768) {
        document.getElementById('sidebar').classList.remove('open');
        document.querySelector('.mobile-menu-btn')?.setAttribute('aria-expanded', 'false');
    }

    // Trigger view-specific initialization
    if (viewId === 'insights' && typeof loadAnalytics === 'function') {
        loadAnalytics();
    } else if (viewId === 'tasks' && typeof loadTasks === 'function') {
        setTimeout(() => loadTasks(), 100);
    }
}

document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target.closest('[data-action], [data-view], [data-suggestion]') : null;
    if (!target) return;

    if (target.dataset.view) {
        switchView(target.dataset.view);
        return;
    }
    if (target.dataset.suggestion) {
        useSuggestion(target.dataset.suggestion);
        return;
    }

    const actions = {
        'open-settings': openSettings,
        'close-settings': closeSettings,
        'toggle-sidebar': toggleSidebar,
        'send-message': sendMessage,
        'stop-generation': stopGeneration,
        'toggle-voice': toggleVoice,
        'clear-chat': clearChatHistory,
        'open-task-modal': openTaskModal,
        'clear-completed': clearCompletedTasks,
        'calendar-prev': prevDay,
        'calendar-next': nextDay,
        'calendar-today': goToToday,
        'calendar-auto': autoSchedule,
        'save-settings': saveSettings,
        'logout': () => { logout(); closeSettings(); },
        'save-task': saveTask,
        'close-task-modal': closeTaskModal,
    };
    const action = target.dataset.action;
    if (action && actions[action]) actions[action]();
});

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        closeSettings();
        closeTaskModal();
    }
});

// Sidebar Toggle (Mobile)
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const isOpen = sidebar.classList.toggle('open');
    document.querySelector('.mobile-menu-btn')?.setAttribute('aria-expanded', String(isOpen));
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
