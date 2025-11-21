async function loadTasks() {
    const res = await fetch('/api/tasks');
    const tasks = await res.json();
    
    const list = document.getElementById('tasks-list');
    list.innerHTML = '';
    
    if (tasks.length === 0) {
        list.innerHTML = '<div class="text-center text-gray-500 py-4">No tasks pending. Enjoy your day!</div>';
        updateStats(0);
        return;
    }

    let completedCount = 0;

    tasks.forEach(t => {
        if (t.completed) completedCount++;
        
        const li = document.createElement('li');
        li.className = 'task-item flex items-center justify-between p-3 bg-[#1e1f20] rounded-lg border border-gray-700 group';
        
        li.innerHTML = `
            <div class="flex items-center gap-3">
                <button onclick="toggleTask(${t.id}, ${!t.completed})" 
                    class="w-5 h-5 rounded border border-gray-500 flex items-center justify-center hover:border-blue-500 transition ${t.completed ? 'bg-blue-500 border-blue-500' : ''}">
                    ${t.completed ? '<i class="fa-solid fa-check text-white text-xs"></i>' : ''}
                </button>
                <div>
                    <p class="${t.completed ? 'line-through' : ''} font-medium">${t.title}</p>
                    ${t.due_date ? `<p class="text-xs text-gray-400"><i class="fa-regular fa-clock"></i> ${new Date(t.due_date).toLocaleString()}</p>` : ''}
                </div>
            </div>
        `;
        list.appendChild(li);
    });

    updateStats(completedCount, tasks.length);
}

async function toggleTask(id, status) {
    await fetch(`/api/tasks/${id}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({completed: status})
    });
    loadTasks();
}

async function addTaskModal() {
    const title = prompt("What needs to be done?");
    if (!title) return;
    
    await fetch('/api/tasks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title: title})
    });
    loadTasks();
    showNotification('Task added');
}

let chartInstance = null;
function updateStats(completed, total) {
    const ctx = document.getElementById('stats-chart').getContext('2d');
    if (chartInstance) chartInstance.destroy();
    
    chartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Done', 'Pending'],
            datasets: [{
                data: [completed, total - completed],
                backgroundColor: ['#3b82f6', '#4b5563'],
                borderWidth: 0
            }]
        },
        options: {
            cutout: '70%',
            plugins: { legend: { display: false } }
        }
    });
}