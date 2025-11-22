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

    setupNavigation();
    setupVoiceInput();
    loadSettings();

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

// Calendar rendering
function renderCalendar() {
    const container = document.getElementById('calendar-grid');
    if (!container) return;

    const date = new Date(currentYear, currentMonth, 1);
    const monthLabel = document.getElementById('current-month');
    if (monthLabel) {
        monthLabel.textContent = date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    }

    const firstDay = date.getDay();
    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();

    let html = '<div class="calendar-grid-inner">';

    // Weekday headers
    ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].forEach(day => {
        html += `<div class="calendar-weekday">${day}</div>`;
    });

    // Empty cells before first day
    for (let i = 0; i < firstDay; i++) {
        html += '<div class="calendar-day empty"></div>';
    }

    // Days
    const today = new Date();
    for (let day = 1; day <= daysInMonth; day++) {
        const isToday = day === today.getDate() &&
            currentMonth === today.getMonth() &&
            currentYear === today.getFullYear();

        html += `<div class="calendar-day${isToday ? ' today' : ''}">
            <div class="day-number">${day}</div>
        </div>`;
    }

    html += '</div>';
    container.innerHTML = html;
}

function previousMonth() {
    currentMonth--;
    if (currentMonth < 0) {
        currentMonth = 11;
        currentYear--;
    }
    renderCalendar();
}

function nextMonth() {
    currentMonth++;
    if (currentMonth > 11) {
        currentMonth = 0;
        currentYear++;
    }
    renderCalendar();
}

async function loadAnalytics() {
    try {
        const analytics = await apiCall('/analytics?days=30');

        document.getElementById('total-completed').textContent = analytics.total_completed || 0;
        document.getElementById('completion-rate').textContent = `${analytics.completion_rate || 0}%`;
        document.getElementById('daily-average').textContent = analytics.average_per_day?.toFixed(1) || 0;
        document.getElementById('total-created').textContent = analytics.total_created || 0;

    } catch (error) {
        console.error('Error loading analytics:', error);
    }
}
