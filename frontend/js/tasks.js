// Task Management Logic

let allTasks = [];
let currentEditId = null;

document.addEventListener('DOMContentLoaded', loadTasks);

async function loadTasks() {
    try {
        const response = await fetch(`${API_URL}/tasks`);
        if (response.ok) {
            const data = await response.json();
            // Handle both array and object responses
            allTasks = Array.isArray(data) ? data : (data.tasks || []);
            renderKanban(allTasks);
        } else {
            const errorText = await response.text();
            console.error("Failed to load tasks:", response.status, errorText);
            // Show empty state gracefully
            allTasks = [];
            renderKanban([]);
            if (typeof showToast === 'function') {
                showToast("Failed to load tasks. Please refresh.", "error");
            }
        }
    } catch (error) {
        console.error("Error loading tasks:", error);
        // Show empty state gracefully
        allTasks = [];
        renderKanban([]);
        if (typeof showToast === 'function') {
            showToast("Connection error. Please check your network.", "error");
        }
    }
}

function renderKanban(tasks) {
    // Support both old and new IDs for compatibility
    const todoList = document.getElementById('todo-list') || document.getElementById('list-todo');
    const doneList = document.getElementById('done-list') || document.getElementById('list-done');

    // Clear lists
    if (todoList) todoList.innerHTML = '';
    if (doneList) doneList.innerHTML = '';

    // Handle empty or invalid tasks array
    if (!tasks || !Array.isArray(tasks)) {
        tasks = [];
    }

    let counts = { todo: 0, done: 0 };

    // Show "No tasks yet" message if array is empty
    if (tasks.length === 0) {
        if (todoList) {
            todoList.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--text-muted);">No tasks yet. Click "+ New Task" to get started!</div>';
        }
        if (doneList) {
            doneList.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--text-muted);">No completed tasks</div>';
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
    div.ondragstart = (e) => drag(e, task.id);

    // Truncate title if too long
    const title = task.title.length > 50 ? task.title.substring(0, 47) + '...' : task.title;
    
    // Truncate description if too long
    const description = task.description ? (task.description.length > 100 ? task.description.substring(0, 97) + '...' : task.description) : '';

    // Date Formatting with color coding
    let dateHtml = '';
    if (task.due_date) {
        const date = new Date(task.due_date);
        const now = new Date();
        const isOverdue = date < now && !task.completed;
        const isFuture = date > now;
        const dateStr = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        const dateClass = isOverdue ? 'overdue' : (isFuture ? 'future' : 'today');
        dateHtml = `<span class="task-date ${dateClass}">
                        <i data-lucide="calendar" style="width: 14px; height: 14px;"></i> ${dateStr}
                    </span>`;
    }

    // Priority badge with proper capitalization
    const priorityLabel = task.priority ? task.priority.charAt(0).toUpperCase() + task.priority.slice(1) : 'Medium';

    // Complete button - show different icon/text based on status
    const completeIcon = task.completed ? 'rotate-ccw' : 'check-circle';
    const completeTitle = task.completed ? 'Mark as Incomplete' : 'Mark as Complete';
    const completeClass = task.completed ? 'complete active' : 'complete';

    div.innerHTML = `
        <div class="task-header">
            <div class="task-title-wrapper">
                <button class="task-checkbox ${task.completed ? 'checked' : ''}" onclick="toggleComplete(${task.id}, ${!task.completed})" title="${completeTitle}">
                    <i data-lucide="${task.completed ? 'check-circle-2' : 'circle'}" style="width: 20px; height: 20px;"></i>
                </button>
                <span class="task-title ${task.completed ? 'completed' : ''}">${escapeHtml(title)}</span>
            </div>
            <div class="task-actions">
                <button class="action-btn" onclick="openEditModal(${task.id})" title="Edit">
                    <i data-lucide="edit-2" style="width: 14px; height: 14px;"></i>
                </button>
                <button class="action-btn delete" onclick="deleteTask(${task.id})" title="Delete">
                    <i data-lucide="trash-2" style="width: 14px; height: 14px;"></i>
                </button>
            </div>
        </div>
        
        <div class="task-body">
            <p class="${task.completed ? 'completed' : ''}">${escapeHtml(description)}</p>
        </div>
        
        <div class="task-footer">
            <div class="task-footer-left">
                ${dateHtml}
                <span class="task-badge priority-${task.priority || 'medium'}">${priorityLabel}</span>
            </div>
        </div>
    `;

    return div;
}

// Helper function to escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            showToast(currentEditId ? "Task updated successfully" : "Task created successfully");
            closeTaskModal();
            loadTasks(); // Refresh the board
        } else {
            const err = await response.json();
            // Handle both 'detail' (FastAPI default) and 'details' (Global Handler)
            const msg = err.detail || err.details || "Failed to save task";
            showToast(msg, "error");
        }
    } catch (error) {
        console.error("Error saving task:", error);
        showToast(error.message || "Error saving task", "error");
    }
}

// --- Actions ---

async function deleteTask(id) {
    if (!confirm("Are you sure you want to delete this task?")) return;

    try {
        const response = await fetch(`${API_URL}/tasks/${id}`, { method: 'DELETE' });
        if (response.ok) {
            showToast("Task deleted successfully");
            loadTasks(); // Refresh the board
        } else {
            const err = await response.json();
            const msg = err.detail || err.details || "Failed to delete task";
            showToast(msg, "error");
        }
    } catch (error) {
        console.error("Error deleting:", error);
        showToast("Error deleting task", "error");
    }
}

async function toggleComplete(id, status) {
    try {
        const response = await fetch(`${API_URL}/tasks/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ completed: status })
        });

        if (response.ok) {
            showToast(status ? "Task completed" : "Task reopened");
            loadTasks(); // Refresh the board
        } else {
            const err = await response.json();
            const msg = err.detail || err.details || "Failed to update task";
            showToast(msg, "error");
        }
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
            fetch(`${API_URL}/tasks/${task.id}`, { method: 'DELETE' })
        );
        
        await Promise.all(deletePromises);
        showToast(`Cleared ${completedTasks.length} completed task(s)`);
        loadTasks(); // Refresh the board
    } catch (error) {
        console.error("Error clearing completed tasks:", error);
        showToast("Error clearing completed tasks", "error");
    }
}

// Export for global access
window.clearCompletedTasks = clearCompletedTasks;
