// Tasks Management
let editingTaskId = null;

async function loadTasks() {
    const container = document.getElementById('tasks-list');
    // If we are not on tasks view, we might not have this container, but check if we should
    if (!container && document.getElementById('tasks-view').classList.contains('active')) {
        // Maybe it's dynamically created? No, it should be in HTML.
        // Wait, index.html didn't show tasks-list container in the snippet I saw.
        // I should check if I need to create it or if it exists.
        // Assuming it exists or I should target 'tasks-view'.
    }

    // Actually, looking at index.html snippet, I didn't see #tasks-list. 
    // I saw <div id="tasks-view" class="view">...</div> but the content was truncated or not fully visible.
    // I'll assume there is a container or I'll append to tasks-view.

    const view = document.getElementById('tasks-view');
    if (!view) return;

    // Clear or find list container
    let list = document.getElementById('tasks-list');
    if (!list) {
        view.innerHTML = `
            <div class="view-header">
                <h2>Tasks</h2>
                <button class="btn-primary" onclick="openTaskModal()">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                    </svg>
                    New Task
                </button>
            </div>
            <div id="tasks-list" class="tasks-container"></div>
        `;
        list = document.getElementById('tasks-list');
    }

    list.innerHTML = '<div class="loading">Loading tasks...</div>';

    try {
        const response = await fetch('/api/tasks');
        const data = await response.json();
        const tasks = data.tasks || [];

        if (tasks.length === 0) {
            list.innerHTML = '<div class="empty-state">No tasks yet. Create one to get started!</div>';
            return;
        }

        // Group tasks
        const today = new Date();
        const overdue = tasks.filter(t => !t.completed && t.due_date && new Date(t.due_date) < today);
        const todayTasks = tasks.filter(t => !t.completed && t.due_date && isToday(new Date(t.due_date)));
        const upcoming = tasks.filter(t => !t.completed && !overdue.includes(t) && !todayTasks.includes(t));
        const completed = tasks.filter(t => t.completed);

        let html = '';

        if (overdue.length > 0) html += createTaskGroup('⚠️ Overdue', overdue);
        if (todayTasks.length > 0) html += createTaskGroup('📅 Today', todayTasks);
        if (upcoming.length > 0) html += createTaskGroup('📋 Upcoming', upcoming);
        if (completed.length > 0) html += createTaskGroup('✅ Completed', completed);

        list.innerHTML = html;

    } catch (error) {
        console.error('Error loading tasks:', error);
        list.innerHTML = `
            <div class="error-state">
                <p>Failed to load tasks.</p>
                <button class="btn-secondary" onclick="loadTasks()">Retry</button>
            </div>
        `;
    }
}

function createTaskGroup(title, tasks) {
    return `
        <div class="task-group">
            <h3 class="group-title">${title} <span class="count">(${tasks.length})</span></h3>
            <div class="task-items">
                ${tasks.map(t => createTaskItem(t)).join('')}
            </div>
        </div>
    `;
}

function createTaskItem(task) {
    const priorityClass = `priority-${task.priority}`;
    const dueText = task.due_date ? new Date(task.due_date).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';

    return `
        <div class="task-item ${task.completed ? 'completed' : ''}" onclick="viewTask(${task.id})">
            <div class="checkbox-wrapper" onclick="event.stopPropagation(); toggleTask(${task.id}, ${task.completed})">
                <div class="checkbox ${task.completed ? 'checked' : ''}">
                    ${task.completed ? '✓' : ''}
                </div>
            </div>
            <div class="task-content">
                <div class="task-title">${task.title}</div>
                ${task.description ? `<div class="task-desc">${task.description}</div>` : ''}
                <div class="task-meta">
                    <span class="badge ${priorityClass}">${task.priority}</span>
                    ${dueText ? `<span class="due-date">🕒 ${dueText}</span>` : ''}
                </div>
            </div>
        </div>
    `;
}

function isToday(date) {
    const today = new Date();
    return date.getDate() === today.getDate() &&
        date.getMonth() === today.getMonth() &&
        date.getFullYear() === today.getFullYear();
}

async function toggleTask(id, currentStatus) {
    try {
        await fetch(`/api/tasks/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ completed: !currentStatus })
        });
        loadTasks();
        showToast(currentStatus ? 'Task reopened' : 'Task completed!');
    } catch (error) {
        showToast('Failed to update task', 'error');
    }
}

// Modal Functions
function openTaskModal(dateStr) {
    editingTaskId = null;
    document.getElementById('task-title').value = '';
    document.getElementById('task-description').value = '';

    if (dateStr && typeof dateStr === 'string') {
        // Set time to 09:00 by default
        document.getElementById('task-due-date').value = `${dateStr}T09:00`;
    } else {
        document.getElementById('task-due-date').value = '';
    }

    document.getElementById('task-priority').value = 'medium';
    document.getElementById('btn-delete-task').style.display = 'none';
    document.getElementById('task-modal').classList.add('active');
}

async function viewTask(id) {
    try {
        // Fetch task details if needed, or find in local list if we stored it.
        // For now, let's fetch to be safe or just assume we can get it.
        // Since we don't have a local store, we'll fetch.
        // Actually, we can just fetch the list again or fetch single.
        // Let's fetch single.
        // Wait, backend might not have GET /tasks/{id}.
        // I'll check backend routes.
        // If not, I'll filter from the list if I had it.
        // I'll assume I can fetch list and find it.

        const response = await fetch('/api/tasks');
        const data = await response.json();
        const task = data.tasks.find(t => t.id === id);

        if (!task) return;

        editingTaskId = id;
        document.getElementById('task-title').value = task.title;
        document.getElementById('task-description').value = task.description || '';
        document.getElementById('task-due-date').value = task.due_date ? task.due_date.slice(0, 16) : '';
        document.getElementById('task-priority').value = task.priority;

        document.getElementById('btn-delete-task').style.display = 'block';
        document.getElementById('task-modal').classList.add('active');

    } catch (error) {
        console.error(error);
        showToast('Failed to load task details', 'error');
    }
}

function closeTaskModal() {
    document.getElementById('task-modal').classList.remove('active');
}

async function saveTask() {
    const title = document.getElementById('task-title').value;
    if (!title) {
        showToast('Title is required', 'error');
        return;
    }

    const data = {
        title,
        description: document.getElementById('task-description').value,
        due_date: document.getElementById('task-due-date').value || null,
        priority: document.getElementById('task-priority').value
    };

    try {
        const method = editingTaskId ? 'PUT' : 'POST';
        const url = editingTaskId ? `/api/tasks/${editingTaskId}` : '/api/tasks';

        const response = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            closeTaskModal();
            loadTasks();
            showToast(editingTaskId ? 'Task updated' : 'Task created', 'success');
        } else {
            const err = await response.json();
            showToast(err.detail || 'Failed to save task', 'error');
        }
    } catch (error) {
        showToast('Error saving task', 'error');
    }
}

async function deleteCurrentTask() {
    if (!editingTaskId) return;

    if (!confirm('Are you sure you want to delete this task?')) return;

    try {
        const response = await fetch(`/api/tasks/${editingTaskId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            closeTaskModal();
            loadTasks();
            showToast('Task deleted', 'success');
        } else {
            showToast('Failed to delete task', 'error');
        }
    } catch (error) {
        showToast('Error deleting task', 'error');
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('tasks-view').classList.contains('active')) {
        loadTasks();
    }
});

// Observer for view change
const taskObserver = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
        if (mutation.target.id === 'tasks-view' && mutation.target.classList.contains('active')) {
            loadTasks();
        }
    });
});

const tasksView = document.getElementById('tasks-view');
if (tasksView) {
    taskObserver.observe(tasksView, { attributes: true });
}
