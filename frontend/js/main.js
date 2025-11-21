// Global state
let currentView = 'chat';
let currentTheme = 'light';
let currentMonth = new Date().getMonth();
let currentYear = new Date().getFullYear();
let editingTaskId = null;

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 AURA Initializing...');
    
    // Setup navigation
    setupNavigation();
    
    // Setup theme toggle
    setupThemeToggle();
    
    // Load initial data
    loadTasks();
    loadSchedule();
    
    // Setup voice input
    setupVoiceInput();
    
    // Setup file upload
    setupFileUpload();
    
    console.log('✅ AURA Ready!');
});

function setupNavigation() {
    const navBtns = document.querySelectorAll('.nav-btn');
    
    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const viewName = btn.getAttribute('data-view');
            switchView(viewName);
        });
    });
}

function switchView(viewName) {
    // Hide all views
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active');
    });
    
    // Show selected view
    document.getElementById(`${viewName}-view`).classList.add('active');
    
    // Update navigation
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-view="${viewName}"]`).classList.add('active');
    
    currentView = viewName;
    
    // Load view-specific data
    if (viewName === 'tasks') {
        loadTasks();
    } else if (viewName === 'calendar') {
        renderCalendar();
    } else if (viewName === 'analytics') {
        loadAnalytics();
    }
}

function setupThemeToggle() {
    const themeToggle = document.getElementById('theme-toggle');
    const icon = themeToggle.querySelector('.icon');
    
    // Load saved theme
    const savedTheme = localStorage.getItem('theme') || 'light';
    applyTheme(savedTheme);
    
    themeToggle.addEventListener('click', () => {
        currentTheme = currentTheme === 'light' ? 'dark' : 'light';
        applyTheme(currentTheme);
        localStorage.setItem('theme', currentTheme);
    });
}

function applyTheme(theme) {
    document.body.classList.remove('light', 'dark');
    document.body.classList.add(theme);
    
    const themeIcon = document.querySelector('#theme-toggle .icon');
    themeIcon.textContent = theme === 'light' ? '🌙' : '☀️';
    
    currentTheme = theme;
}

// Toast notifications
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Fill chat input (from suggestion chips)
function fillInput(text) {
    document.getElementById('chat-input').value = text;
    document.getElementById('chat-input').focus();
}

// Format date for display
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

// Format time
function formatTime(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleTimeString('en-US', { 
        hour: 'numeric', 
        minute: '2-digit',
        hour12: true
    });
}

// Priority badge colors
function getPriorityClass(priority) {
    const classes = {
        'urgent': 'priority-urgent',
        'high': 'priority-high',
        'medium': 'priority-medium',
        'low': 'priority-low'
    };
    return classes[priority] || 'priority-medium';
}

// API helper
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
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        showToast('Network error. Please try again.', 'error');
        throw error;
    }
}

// Calendar rendering
function renderCalendar() {
    const grid = document.getElementById('calendar-grid');
    const monthLabel = document.getElementById('current-month');
    
    // Update month label
    const date = new Date(currentYear, currentMonth, 1);
    monthLabel.textContent = date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    
    // Get first day of month and number of days
    const firstDay = date.getDay();
    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
    
    // Create calendar HTML
    let html = '<div class="calendar-weekdays">';
    ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].forEach(day => {
        html += `<div class="weekday">${day}</div>`;
    });
    html += '</div><div class="calendar-days">';
    
    // Empty cells before month starts
    for (let i = 0; i < firstDay; i++) {
        html += '<div class="calendar-day empty"></div>';
    }
    
    // Days of the month
    const today = new Date();
    for (let day = 1; day <= daysInMonth; day++) {
        const isToday = day === today.getDate() && 
                       currentMonth === today.getMonth() && 
                       currentYear === today.getFullYear();
        
        html += `<div class="calendar-day${isToday ? ' today' : ''}" data-date="${currentYear}-${currentMonth + 1}-${day}">
            <div class="day-number">${day}</div>
            <div class="day-tasks" id="day-${currentYear}-${currentMonth + 1}-${day}"></div>
        </div>`;
    }
    
    html += '</div>';
    grid.innerHTML = html;
    
    // Load tasks for this month
    loadCalendarTasks();
}

async function loadCalendarTasks() {
    try {
        const tasks = await apiCall('/tasks?completed=false');
        
        // Clear existing task indicators
        document.querySelectorAll('.day-tasks').forEach(el => el.innerHTML = '');
        
        // Add task indicators
        tasks.forEach(task => {
            if (task.due_date) {
                const dueDate = new Date(task.due_date);
                if (dueDate.getMonth() === currentMonth && dueDate.getFullYear() === currentYear) {
                    const dayId = `day-${dueDate.getFullYear()}-${dueDate.getMonth() + 1}-${dueDate.getDate()}`;
                    const dayEl = document.getElementById(dayId);
                    if (dayEl) {
                        const dot = document.createElement('div');
                        dot.className = `task-dot ${task.priority}`;
                        dot.title = task.title;
                        dayEl.appendChild(dot);
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error loading calendar tasks:', error);
    }
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

// Load schedule
async function loadSchedule() {
    try {
        const schedule = await apiCall('/schedule');
        console.log('Schedule loaded:', schedule);
        // Update UI if needed
    } catch (error) {
        console.error('Error loading schedule:', error);
    }
}

// Analytics
async function loadAnalytics() {
    try {
        const analytics = await apiCall('/analytics?days=30');
        
        // Update stat cards
        document.getElementById('total-completed').textContent = analytics.total_completed || 0;
        document.getElementById('completion-rate').textContent = `${analytics.completion_rate || 0}%`;
        document.getElementById('daily-average').textContent = analytics.average_per_day?.toFixed(1) || 0;
        document.getElementById('total-created').textContent = analytics.total_created || 0;
        
        // Render priority breakdown
        renderPriorityChart(analytics.priority_breakdown || {});
        
        // Render activity chart (simple bar chart)
        renderActivityChart(analytics.tasks_by_day || {});
        
    } catch (error) {
        console.error('Error loading analytics:', error);
    }
}

function renderPriorityChart(breakdown) {
    const container = document.getElementById('priority-chart');
    const total = Object.values(breakdown).reduce((sum, val) => sum + val, 0);
    
    if (total === 0) {
        container.innerHTML = '<p class="no-data">No data available</p>';
        return;
    }
    
    let html = '';
    const priorities = ['urgent', 'high', 'medium', 'low'];
    
    priorities.forEach(priority => {
        const count = breakdown[priority] || 0;
        const percentage = (count / total * 100).toFixed(1);
        
        html += `
            <div class="priority-bar">
                <div class="priority-label">
                    <span class="priority-name ${priority}">${priority.charAt(0).toUpperCase() + priority.slice(1)}</span>
                    <span class="priority-count">${count} (${percentage}%)</span>
                </div>
                <div class="priority-fill-container">
                    <div class="priority-fill ${priority}" style="width: ${percentage}%"></div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

function renderActivityChart(tasksByDay) {
    // Simple canvas-based chart
    const canvas = document.getElementById('activity-chart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const width = canvas.width = canvas.offsetWidth;
    const height = canvas.height = 300;
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    const days = Object.keys(tasksByDay).sort().slice(-30); // Last 30 days
    const values = days.map(day => tasksByDay[day] || 0);
    const maxValue = Math.max(...values, 1);
    
    const barWidth = width / days.length;
    const maxBarHeight = height - 40;
    
    // Draw bars
    ctx.fillStyle = '#4a9eff';
    values.forEach((value, index) => {
        const barHeight = (value / maxValue) * maxBarHeight;
        const x = index * barWidth;
        const y = height - barHeight - 20;
        
        ctx.fillRect(x + 2, y, barWidth - 4, barHeight);
    });
    
    // Draw labels
    ctx.fillStyle = '#666';
    ctx.font = '10px Arial';
    ctx.textAlign = 'center';
    
    days.forEach((day, index) => {
        if (index % 3 === 0) { // Show every 3rd label to avoid crowding
            const x = index * barWidth + barWidth / 2;
            const label = new Date(day).getDate();
            ctx.fillText(label, x, height - 5);
        }
    });
}
