document.addEventListener('DOMContentLoaded', () => {
    navigate('chat'); // Default
    loadTasks();
    document.getElementById('current-date').textContent = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
});

function navigate(sectionId) {
    // Hide all sections
    document.querySelectorAll('.section').forEach(el => el.classList.add('hidden'));
    // Show target
    document.getElementById(`section-${sectionId}`).classList.remove('hidden');
    
    // Update Sidebar
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    // This is a simple check, ideally add IDs to buttons
    const navIndex = {'chat':0, 'dashboard':1, 'files':2}[sectionId];
    if(navIndex !== undefined) document.querySelectorAll('.nav-item')[navIndex].classList.add('active');
}

function showNotification(msg, type='info') {
    const el = document.getElementById('notification');
    document.getElementById('notif-msg').textContent = msg;
    el.classList.remove('hidden');
    setTimeout(() => el.classList.add('hidden'), 3000);
}