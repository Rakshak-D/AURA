// Keyboard shortcuts for AURA

document.addEventListener('DOMContentLoaded', () => {
    setupKeyboardShortcuts();
});

function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + K: Focus chat
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            document.getElementById('chat-input')?.focus();
        }

        // Ctrl/Cmd + N: New task
        if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
            e.preventDefault();
            openTaskModal();
        }

        // Ctrl/Cmd + /: Show shortcuts help
        if ((e.ctrlKey || e.metaKey) && e.key === '/') {
            e.preventDefault();
            showShortcutsHelp();
        }

        // Ctrl/Cmd + 1-5: Switch views
        if ((e.ctrlKey || e.metaKey) && e.key >= '1' && e.key <= '5') {
            e.preventDefault();
            const views = ['chat', 'tasks', 'calendar', 'upload', 'analytics'];
            const index = parseInt(e.key) - 1;
            if (views[index]) {
                switchView(views[index]);
            }
        }

        // Esc: Close modals
        if (e.key === 'Escape') {
            closeTaskModal();
            closeSettings();
        }
    });
}

function showShortcutsHelp() {
    const shortcuts = `
**AURA Keyboard Shortcuts:**

• Ctrl+K - Focus chat
• Ctrl+N - New task
• Ctrl+1-5 - Switch between views
• Ctrl+/ - Show this help
• Esc - Close modals
    `.trim();

    showToast(shortcuts);
}
