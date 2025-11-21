// Task management
let allTasks = [];
let currentFilter = 'all';

async function loadTasks() {
    const list = document.getElementById('tasks-list');
    list.innerHTML = '<div class="loading">Loading tasks...</div>';
    
    try {
        const tasks = await apiCall('/tasks');
        allTasks = tasks;
        renderTasks(tasks);
    } catch (error) {
        list.innerHTML = '<div class="error">Failed to load tasks. Please try again.</div>';
        console.error('Error loading tasks:', error);
    }
}

function renderTasks(tasks) {
    const list = document.getElementById('tasks-list');
    
    if (tasks.length === 0) {
        list.innerHTML = `
            <div class="empty-tasks">
                <div class="empty-icon">✨</div>
                <p>No tasks yet. Create one to get started!</p>
            </div>
        `;
        return;
    }
    
    // Group tasks
    const overdue = tasks.filter(t => !t.completed && t.due_date && new Date(t.due_date) < new Date());
    const today = tasks.filter(t => !t.completed && t.due_date && isToday(new Date(t.due_date)));
    const upcoming = tasks.filter(t => !t.completed && t.due_date && new Date(t.due_date) > new Date() && !isToday(new Date(t.due_date)));
    const noDate = tasks.filter(t => !t.completed && !t.due_date);
    const completed = tasks.filter(t => t.completed);
    
    let html = '';
    
    if (overdue.length > 0) {
        html += renderTaskGroup('⚠️ Overdue', overdue, 'overdue');
    }
    if (today.length > 0) {
        html += renderTaskGroup('📅 Today', today, 'today');
    }
    if (upcoming.length > 0) {
        html += renderTaskGroup('📆 Upcoming', upcoming, 'upcoming');
    }
    if (noDate.length > 0) {
        html += renderTaskGroup('📝 No Due Date', noDate, 'no-date');
    }
    if (completed.length > 0) {
        html += renderTaskGroup('✅ Completed', completed, 'completed');
    }
    
    list.innerHTML = html;
}

function renderTaskGroup(title, tasks, className) {
    let html = `<div class="task-group ${className}">
        <h3 class="task-group-title">${title} <span class="task-count">(${tasks.length})</span></h3>
        <div class="task-items">`;
    
    tasks.forEach(task => {
        const tags = task.tags && task.tags.length > 0 
            ? task.tags.map(tag => `<span class="task-tag">#${tag}</span>`).join('')
            : '';
        
        html += `
            <div class="task-item ${task.completed ? 'completed' : ''}" data-task-id="${task.id}">
                <input 
                    type="checkbox" 
                    class="task-checkbox" 
                    ${task.completed ? 'checked' : ''}
                    onchange="toggleTask(${task.id}, ${!task.completed})"
                >
                <div class="task-details">
                    <div class="task-title">${task.title}</div>
                    ${task.description ? `<div class="task-description">${task.description}</div>` : ''}
                    <div class="task-meta">
                        <span class="task-priority ${getPriorityClass(task.priority)}">${task.priority}</span>
                        ${task.due_date ? `<span class="task-due">${formatDate(task.due_date)} ${formatTime(task.due_date)}</span>` : ''}
                        ${task.recurring ? `<span class="task-recurring">🔄 ${task.recurring}</span>` : ''}
                        ${tags}
                    </div>
                </div>
                <div class="task-actions">
                    <button class="task-action-btn" onclick="editTask(${task.id})" title="Edit">
                        ✏️
                    </button>
                    <button class="task-action-btn" onclick="deleteTask(${task.id})" title="Delete">
                        🗑️
                    </button>
                </div>
            </div>
        `;
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

async function toggleTask(taskId, completed) {
    try {
        await apiCall(`/tasks/${taskId}`, 'PUT', { completed });
        showToast(completed ? '✅ Task completed!' : '🔄 Task marked as incomplete');
        loadTasks();
    } catch (error) {
        showToast('Failed to update task', 'error');
    }
}

function openTaskModal(taskId = null) {
    const modal = document.getElementById('task-modal');
    const modalTitle = document.getElementById('modal-title');
    
    if (taskId) {
        // Edit mode
        editingTaskId = taskId;
        modalTitle.textContent = 'Edit Task';
        
        const task = allTasks.find(t => t.id === taskId);
        if (task) {
            document.getElementById('task-title').value = task.title;
            document.getElementById('task-description').value = task.description || '';
            document.getElementById('task-due-date').value = task.due_date ? new Date(task.due_date).toISOString().slice(0, 16) : '';
            document.getElementById('task-priority').value = task.priority;
            document.getElementById('task-tags').value = task.tags ? task.tags.join(', ') : '';
            document.getElementById('task-recurring').value = task.recurring || '';
        }
    } else {
        // Create mode
        editingTaskId = null;
        modalTitle.textContent = 'Add New Task';
        
        // Clear form
        document.getElementById('task-title').value = '';
        document.getElementById('task-description').value = '';
        document.getElementById('task-due-date').value = '';
        document.getElementById('task-priority').value = 'medium';
        document.getElementById('task-tags').value = '';
        document.getElementById('task-recurring').value = '';
    }
    
    modal.style.display = 'flex';
}

function closeTaskModal() {
    document.getElementById('task-modal').style.display = 'none';
    editingTaskId = null;
}

async function saveTask() {
    const title = document.getElementById('task-title').value.trim();
    
    if (!title) {
        showToast('Please enter a task title', 'error');
        return;
    }
    
    const taskData = {
        title,
        description: document.getElementById('task-description').value.trim() || null,
        due_date: document.getElementById('task-due-date').value || null,
        priority: document.getElementById('task-priority').value,
        tags: document.getElementById('task-tags').value.split(',').map(t => t.trim()).filter(t => t),
        recurring: document.getElementById('task-recurring').value || null
    };
    
    try {
        if (editingTaskId) {
            // Update existing task
            await apiCall(`/tasks/${editingTaskId}`, 'PUT', taskData);
            showToast('✅ Task updated!');
        } else {
            // Create new task
            await apiCall('/tasks', 'POST', taskData);
            showToast('✅ Task created!');
        }
        
        closeTaskModal();
        loadTasks();
        
    } catch (error) {
        showToast('Failed to save task', 'error');
    }
}

function editTask(taskId) {
    openTaskModal(taskId);
}

async function deleteTask(taskId) {
    if (!confirm('Are you sure you want to delete this task?')) {
        return;
    }
    
    try {
        await apiCall(`/tasks/${taskId}`, 'DELETE');
        showToast('🗑️ Task deleted');
        loadTasks();
    } catch (error) {
        showToast('Failed to delete task', 'error');
    }
}

function filterTasks() {
    const filter = document.getElementById('task-filter').value;
    currentFilter = filter;
    
    let filtered = allTasks;
    
    switch (filter) {
        case 'active':
            filtered = allTasks.filter(t => !t.completed);
            break;
        case 'completed':
            filtered = allTasks.filter(t => t.completed);
            break;
        case 'high':
            filtered = allTasks.filter(t => t.priority === 'high' && !t.completed);
            break;
        case 'urgent':
            filtered = allTasks.filter(t => t.priority === 'urgent' && !t.completed);
            break;
    }
    
    renderTasks(filtered);
}

async function searchTasks() {
    const query = document.getElementById('task-search').value.trim();
    
    if (!query) {
        renderTasks(allTasks);
        return;
    }
    
    const filtered = allTasks.filter(task => 
        task.title.toLowerCase().includes(query.toLowerCase()) ||
        (task.description && task.description.toLowerCase().includes(query.toLowerCase()))
    );
    
    renderTasks(filtered);
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('task-modal');
    if (event.target === modal) {
        closeTaskModal();
    }
}
