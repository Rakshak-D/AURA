async function addTask() {
    const title = prompt('Task title:');
    const res = await fetch('/api/tasks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title: title})
    });
    loadTasks();  // Refresh
}