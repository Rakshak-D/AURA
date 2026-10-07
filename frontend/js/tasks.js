// Task Management Logic

let allTasks = [];
let currentEditId = null;

document.addEventListener('DOMContentLoaded', loadTasks);

async function loadTasks() {
    try {
        const data = await apiJson(`${API_URL}/tasks`);
        if (!Array.isArray(data)) throw new Error('Invalid tasks response');
        allTasks = data;
        renderKanban(allTasks);
    } catch (error) {
        console.error("Error loading tasks:", error);
        renderTaskState(error.message || 'Failed to load tasks');
        if (typeof showToast === 'function') {
            showToast("Failed to load tasks. Please refresh.", "error");
        }
    }
}

function renderTaskState(message) {
    const todoList = document.getElementById('todo-list') || document.getElementById('list-todo');
    const doneList = document.getElementById('done-list') || document.getElementById('list-done');
    [todoList, doneList].forEach((list) => {
        if (list) AuraSafe.clear(list).appendChild(AuraSafe.element('div', 'error-state', message));
    });
}

function renderKanban(tasks) {
    // Support both old and new IDs for compatibility
    const todoList = document.getElementById('todo-list') || document.getElementById('list-todo');
    const doneList = document.getElementById('done-list') || document.getElementById('list-done');

    // Clear lists
    if (todoList) AuraSafe.clear(todoList);
    if (doneList) AuraSafe.clear(doneList);

    // Handle empty or invalid tasks array
    if (!tasks || !Array.isArray(tasks)) {
        tasks = [];
    }

    let counts = { todo: 0, done: 0 };

    // Show "No tasks yet" message if array is empty
    if (tasks.length === 0) {
        if (todoList) {
            todoList.appendChild(AuraSafe.element('div', 'empty-state', 'No tasks yet. Click "+ New Task" to get started!'));
        }
        if (doneList) {
            doneList.appendChild(AuraSafe.element('div', 'empty-state', 'No completed tasks'));
        }
    } else {
        tasks.forEach(task => {
            try {
                const card = createTaskCard(task);
                if (!card) return;  // Skip if card creation failed

                // Use completed boolean to determine column
                if (task.completed === true) {
                    if (doneList) doneList.appendChild(card);
                    counts.done++;
                } else {
                    // All non-completed tasks go to "To Do"
                    if (todoList) todoList.appendChild(card);
                    counts.todo++;
                }
            } catch (error) {
                console.error("Error rendering task card:", task, error);
            }
        });
    }

    // Update counts (safely handle missing elements)
    const todoCountEl = document.getElementById('count-todo');
    const doneCountEl = document.getElementById('count-done');
    if (todoCountEl) todoCountEl.textContent = counts.todo;
    if (doneCountEl) doneCountEl.textContent = counts.done;

    // Re-initialize icons
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}

function createTaskCard(task) {
    const div = document.createElement('div');
    div.className = 'task-card';
    div.draggable = true;
    div.dataset.taskId = task.id;
    div.dataset.priority = task.priority;
    div.addEventListener('dragstart', (e) => drag(e, task.id));

    // Truncate title if too long
    const title = task.title.length > 50 ? task.title.substring(0, 47) + '...' : task.title;
    
    // Truncate description if too long
    const description = task.description ? (task.description.length > 100 ? task.description.substring(0, 97) + '...' : task.description) : '';

    // Date Formatting with color coding
    let dateClass = '';
    if (task.due_date) {
        const date = new Date(task.due_date);
        const now = new Date();
        const isOverdue = date < now && !task.completed;
        const isFuture = date > now;
        dateClass = isOverdue ? 'overdue' : (isFuture ? 'future' : 'today');
    }

    // Priority badge with proper capitalization
    const priorityLabel = task.priority ? task.priority.charAt(0).toUpperCase() + task.priority.slice(1) : 'Medium';

    const header = AuraSafe.element('div', 'task-header');
    const titleWrapper = AuraSafe.element('div', 'task-title-wrapper');
    const checkbox = AuraSafe.element('button', `task-checkbox ${task.completed ? 'checked' : ''}`);
    checkbox.type = 'button';
    checkbox.title = task.completed ? 'Mark as Incomplete' : 'Mark as Complete';
    checkbox.setAttribute('aria-label', checkbox.title);
    checkbox.addEventListener('click', () => toggleComplete(task.id, !task.completed));
    const icon = AuraSafe.element('i');
    icon.dataset.lucide = task.completed ? 'check-circle-2' : 'circle';
    icon.style.cssText = 'width:20px;height:20px';
    checkbox.appendChild(icon);
    const titleEl = AuraSafe.element('span', `task-title ${task.completed ? 'completed' : ''}`, title);
    titleWrapper.append(checkbox, titleEl);
    const actions = AuraSafe.element('div', 'task-actions');
    const edit = AuraSafe.element('button', 'action-btn');
    edit.type = 'button';
    edit.title = 'Edit';
    edit.setAttribute('aria-label', 'Edit task');
    edit.addEventListener('click', () => openEditModal(task.id));
    const editIcon = AuraSafe.element('i');
    editIcon.dataset.lucide = 'edit-2';
    edit.appendChild(editIcon);
    const remove = AuraSafe.element('button', 'action-btn delete');
    remove.type = 'button';
    remove.title = 'Delete';
    remove.setAttribute('aria-label', 'Delete task');
    remove.addEventListener('click', () => deleteTask(task.id));
    const removeIcon = AuraSafe.element('i');
    removeIcon.dataset.lucide = 'trash-2';
    remove.appendChild(removeIcon);
    actions.append(edit, remove);
    header.append(titleWrapper, actions);
    const body = AuraSafe.element('div', 'task-body');
    body.appendChild(AuraSafe.element('p', task.completed ? 'completed' : '', description));
    const footer = AuraSafe.element('div', 'task-footer');
    const footerLeft = AuraSafe.element('div', 'task-footer-left');
    if (task.due_date) {
        const dateEl = AuraSafe.element('span', `task-date ${dateClass}`, new Date(task.due_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }));
        footerLeft.appendChild(dateEl);
    }
    footerLeft.appendChild(AuraSafe.element('span', `task-badge priority-${['low', 'medium', 'high', 'urgent'].includes(task.priority) ? task.priority : 'medium'}`, priorityLabel));
    footer.appendChild(footerLeft);
    div.append(header, body, footer);

    return div;
}

// --- Modal Functions ---

function openTaskModal() {
    currentEditId = null;
    document.getElementById('task-modal-title').textContent = "New Task";
    document.getElementById('task-title').value = "";
    document.getElementById('task-desc').value = "";
    document.getElementById('task-date').value = "";
    document.getElementById('task-priority').value = "medium";
    document.getElementById('task-duration').value = "30";

    document.getElementById('task-modal').classList.add('active');
    lucide.createIcons();
}

function openEditModal(id) {
    const task = allTasks.find(t => t.id === id);
    if (!task) {
        showToast("Task not found", "error");
        return;
    }

    currentEditId = id;
    document.getElementById('task-modal-title').textContent = "Edit Task";
    document.getElementById('task-title').value = task.title || "";
    document.getElementById('task-desc').value = task.description || "";

    if (task.due_date) {
        // Format for datetime-local: YYYY-MM-DDTHH:MM
        const date = new Date(task.due_date);
        const iso = date.toISOString().slice(0, 16);
        document.getElementById('task-date').value = iso;
    } else {
        document.getElementById('task-date').value = "";
    }

    document.getElementById('task-priority').value = task.priority || "medium";
    document.getElementById('task-duration').value = task.duration_minutes || 30;

    document.getElementById('task-modal').classList.add('active');
    lucide.createIcons();
}

function closeTaskModal() {
    document.getElementById('task-modal').classList.remove('active');
    currentEditId = null;
}

// Close modal when clicking outside
document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('task-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeTaskModal();
            }
        });
        
        // Close on ESC key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.classList.contains('active')) {
                closeTaskModal();
            }
        });
    }
});

async function saveTask() {
    const title = document.getElementById('task-title').value.trim();
    const desc = document.getElementById('task-desc').value.trim();
    const date = document.getElementById('task-date').value;
    const priority = document.getElementById('task-priority').value;
    const duration = document.getElementById('task-duration').value;

    if (!title) {
        showToast("Title is required", "error");
        return;
    }

    // Parse duration to integer, default to 30 if invalid
    let duration_minutes = 30;
    if (duration) {
        const parsed = parseInt(duration, 10);
        if (!isNaN(parsed) && parsed > 0) {
            duration_minutes = parsed;
        }
    }

    // Format due_date properly - convert datetime-local to ISO format
    let due_date = null;
    if (date) {
        // datetime-local format: YYYY-MM-DDTHH:MM
        // Convert to ISO format for backend
        due_date = new Date(date).toISOString();
    }

    // Ensure payload matches Pydantic TaskCreate model exactly
    const payload = {
        title: title,
        description: desc || null,
        due_date: due_date,  // ISO string or null
        priority: priority || 'medium',
        category: 'Personal',  // Default category
        duration_minutes: duration_minutes,
        tags: []  // Empty array by default
    };
    
    // Log payload for debugging
    console.log('[TASK SAVE] Payload:', JSON.stringify(payload, null, 2));

    try {
        let url = `${API_URL}/tasks`;
        let method = 'POST';

        if (currentEditId) {
            url = `${API_URL}/tasks/${currentEditId}`;
            method = 'PUT';
        }

        await apiJson(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        showToast(currentEditId ? "Task updated successfully" : "Task created successfully");
        closeTaskModal();
        await loadTasks();
    } catch (error) {
        console.error("Error saving task:", error);
        showToast(error.message || "Error saving task", "error");
    }
}

// --- Actions ---

async function deleteTask(id) {
    if (!confirm("Are you sure you want to delete this task?")) return;

    try {
        await apiJson(`${API_URL}/tasks/${id}`, { method: 'DELETE' });
        showToast("Task deleted successfully");
        await loadTasks();
    } catch (error) {
        console.error("Error deleting:", error);
        showToast("Error deleting task", "error");
    }
}

async function toggleComplete(id, status) {
    try {
        await apiJson(`${API_URL}/tasks/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ completed: status })
        });

        showToast(status ? "Task completed" : "Task reopened");
        await loadTasks();
    } catch (error) {
        console.error("Error toggling complete:", error);
        showToast("Error updating task", "error");
    }
}

// --- Drag & Drop ---
function drag(ev, id) {
    ev.dataTransfer.setData("text", id);
}

// Clear Completed Tasks
async function clearCompletedTasks() {
    const completedTasks = allTasks.filter(t => t.completed === true);
    
    if (completedTasks.length === 0) {
        showToast("No completed tasks to clear", "error");
        return;
    }

    if (!confirm(`Are you sure you want to delete ${completedTasks.length} completed task(s)?`)) {
        return;
    }

    try {
        // Delete all completed tasks
        const deletePromises = completedTasks.map(task =>
            apiJson(`${API_URL}/tasks/${task.id}`, { method: 'DELETE' })
        );
        await Promise.all(deletePromises);
        showToast(`Cleared ${completedTasks.length} completed task(s)`);
        await loadTasks();
    } catch (error) {
        console.error("Error clearing completed tasks:", error);
        showToast("Error clearing completed tasks", "error");
    }
}

// Export for global access
window.clearCompletedTasks = clearCompletedTasks;
