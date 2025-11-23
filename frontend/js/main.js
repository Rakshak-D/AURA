// Updated main.js with all fixes

// Global utility functions
function getPriorityClass(priority) {
    const classes = {
        'urgent': 'priority-urgent',
        'high': 'priority-high',
        'medium': 'priority-medium',
        'low': 'priority-low'
    };
    return classes[priority] || 'priority-medium';
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = date - now;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) return 'Today';
    if (days === 1) return 'Tomorrow';
    if (days === -1) return 'Yesterday';
    if (days < -1) return `${Math.abs(days)} days ago`;
    if (days > 1 && days < 7) return `In ${days} days`;

    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
    });
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    if (!toast) return;

    toast.textContent = message;
    toast.className = `toast ${type} show`;

    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

async function apiCall(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json'
        }
    };

    if (data) {
        options.body = JSON.stringify(data);
    }

    try {
        const response = await fetch(`/api${endpoint}`, options);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        showToast('Network error. Please try again.', 'error');
        throw error;
    }
}

// Global state
let currentView = 'chat';
let currentMonth = new Date().getMonth();
let currentYear = new Date().getFullYear();
let sidebarCollapsed = false;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 AURA Initializing...');

    try {
        if (typeof setupNavigation === 'function') {
            setupNavigation();
        } else {
            console.warn('setupNavigation not found');
        }
    } catch (e) {
        console.error('Error setting up navigation:', e);
    }

    try {
        if (typeof setupVoiceInput === 'function') {
            setupVoiceInput();
        } else {
            console.warn('setupVoiceInput not found');
        }
    } catch (e) {
        console.error('Error setting up voice input:', e);
    }

    try {
        if (typeof setupFileUpload === 'function') {
            setupFileUpload();
        } else {
            console.warn('setupFileUpload not found');
        }
    } catch (e) {
        console.error('Error setting up file upload:', e);
    }

    try {
        if (typeof loadSettings === 'function') {
            loadSettings();
        } else {
            console.warn('loadSettings function not found');
        }
    } catch (e) {
        console.error('Error loading settings:', e);
    }

    // Force initial view to ensure UI is visible
    switchView('chat');

    console.log('✅ AURA Ready!');
});

function setupNavigation() {
    const navBtns = document.querySelectorAll('.nav-item');

    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const viewName = btn.getAttribute('data-view');
            switchView(viewName);
        });
    });
}

function switchView(viewName) {
    // Update views
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active');
    });

    const targetView = document.getElementById(`${viewName}-view`);
    if (targetView) {
        targetView.classList.add('active');
    }

    // Update nav    
    document.querySelectorAll('.nav-item').forEach(btn => {
        btn.classList.remove('active');
    });
    const activeBtn = document.querySelector(`[data-view="${viewName}"]`);
    if (activeBtn) {
        activeBtn.classList.add('active');
    }

    currentView = viewName;

    // Load view-specific data
    if (viewName === 'tasks') {
        loadTasks();
    } else if (viewName === 'calendar') {
        renderCalendar();
    } else if (viewName === 'analytics') {
        loadAnalytics();
    } else if (viewName === 'upload') {
        loadUploadedFiles();
    }
}

function toggleSidebar() {
    sidebarCollapsed = !sidebarCollapsed;
    const sidebar = document.querySelector('.sidebar');
    const mainContent = document.querySelector('.main-content');

    if (sidebar && mainContent) {
        sidebar.classList.toggle('collapsed');
        mainContent.classList.toggle('sidebar-collapsed');
    }
}

// Calendar rendering is now handled in calendar.js

// Analytics logic is now handled in analytics.js
