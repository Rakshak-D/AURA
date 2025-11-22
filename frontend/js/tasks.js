// Complete tasks.js with proper API integration

let editingTaskId = null;

async function loadTasks() {
    const container = document.getElementById('tasks-list');
    if (!container) return;

    container.innerHTML = '<div class="loading">Loading tasks...</div>';

    try {
        const response = await apiCall('/tasks');
        const tasks = response.tasks || response || [];

        if (tasks.length === 0) {
            container.innerHTML = '<div class="empty-tasks">No tasks yet. Create one to get started!</div>';
            return;
        }

        // Group tasks
        const today = new Date();
        const overdue = tasks.filter(t => !t.completed && t.due_date && new Date(t.due_date) < today);
        const todayTasks = tasks.filter(t => !t.completed && t.due_date && isToday(new Date(t.due_date)));
        const upcoming = tasks.filter(t => !t.completed && !overdue.includes(t) && !todayTasks.includes(t));
        const completed = tasks.filter(t => t.completed);

        let html = '';

        if (overdue.length > 0) {
            html += createTaskGroup('⚠️ Overdue', overdue);
        }

        if (todayTasks.length > 0) {
            html += createTaskGroup('📅 Today', todayTasks);
        }

        if (upcoming.length > 0) {
            html += createTaskGroup('📋 Upcoming', upcoming);
        }

        if (completed.length > 0) {
            html += createTaskGroup('✅ Completed', completed);
        }

        container.innerHTML = html || '<div class="empty-tasks">No tasks found</div>';

    } catch (error) {
        console.error('Error loading tasks:', error);
        container.innerHTML = '<div class="error">Failed to load tasks. Check if server is running.</div>';
    }
}

function createTaskGroup(title, tasks) {
    let html = `<div class="task-group">
        <div class="task-group-title">${title} <span class="task-count">(${tasks.length})</span></div>
        <div class="task-items">`;

    tasks.forEach(task => {
        const priorityClass = getPriorityClass(task.priority);
        const dueText = task.due_date ? formatDate(task.due_date) : '';

        html += `<div class="task-item ${task.completed ? 'completed' : ''}" onclick="viewTask(${task.id})">
            <div class="task-checkbox" onclick="event.stopPropagation(); toggleTask(${task.id}, ${task.completed})">
                ${task.completed ? '✓' : ''}
            </div>
            <div class="task-content">
                <div class="task-title">${task.title}</div>
                ${task.description ? `<div class="task-description">${task.description}</div>` : ''}
                <div class="task-meta">
                    <span class="task-priority ${priorityClass}">${task.priority}</span>
                    ${dueText ? `<span class="task-due">${dueText}</span>` : ''}
                </div>
            </div>
        </div>`;
    });

    html += '</div></div>';
    return html;
}

function isToday(date) {
    const today = new Date();
    return date.getDate() === today.getDate() &&
        date.getMonth() === today.getMonth() &&
        date.getFullYear() === today.getFullYear();
}

async function toggleTask(taskId, currentStatus) {
    try {
        await apiCall(`/tasks/${taskId}`, 'PUT', { completed: !currentStatus });
        loadTasks();
        showToast(currentStatus ? 'Task reopened' : 'Task completed! 🎉');
    } catch (error) {
        showToast('Failed to update task', 'error');
    }
}

function viewTask(taskId) {
    editingTaskId = taskId;
    showToast('Task viewing - coming soon!');
}

function openTaskModal() {
    const modal = document.getElementById('task-modal');
    if (modal) {
        editingTaskId = null;
        document.getElementById('task-title').value = '';
        document.getElementById('task-description').value = '';
        document.getElementById('task-due-date').value = '';
        document.getElementById('task-priority').value = 'medium';
        modal.classList.add('active');
    }
}

function closeTaskModal() {
    const modal = document.getElementById('task-modal');
    if (modal) {
        modal.classList.remove('active');
    }
}

async function saveTask() {
    const title = document.getElementById('task-title').value.trim();
    if (!title) {
        showToast('Please enter a task title', 'error');
        return;
    }

    const taskData = {
        title,
        description: document.getElementById('task-description').value.trim(),
        due_date: document.getElementById('task-due-date').value || null,
        priority: document.getElementById('task-priority').value
    };

    try {
        if (editingTaskId) {
            await apiCall(`/tasks/${editingTaskId}`, 'PUT', taskData);
            showToast('Task updated!');
        } else {
            await apiCall('/tasks', 'POST', taskData);
            showToast('Task created! 🎯');
        }

        closeTaskModal();

        // Reload tasks if on tasks view
        if (currentView === 'tasks') {
            loadTasks();
        }

    } catch (error) {
        console.error('Save task error:', error);
        showToast('Failed to save task', 'error');
    }
}
