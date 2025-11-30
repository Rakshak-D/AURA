// Settings Management

// Settings Management

// API_URL is defined in main.js

// Load settings on window load (ensures all elements exist)
window.addEventListener('load', loadSettings);
document.addEventListener('DOMContentLoaded', loadSettings);

async function loadSettings() {
    try {
        const response = await fetch(`${API_URL}/settings`);
        if (response.ok) {
            const settings = await response.json();

            // Apply Theme
            // (Currently theme is CSS-based, but we could toggle classes if needed)

            // Populate Modal Inputs - support both old and new IDs
            const usernameInput = document.getElementById('setting-username') || document.getElementById('settings-username');
            const themeInput = document.getElementById('setting-theme');
            const voiceInput = document.getElementById('setting-voice');
            const tempInput = document.getElementById('settings-temp');

            if (usernameInput) usernameInput.value = settings.username || 'User';
            if (themeInput) themeInput.value = settings.theme || 'dark';
            if (voiceInput) voiceInput.value = settings.voice || 'enabled';
            if (tempInput) tempInput.value = settings.ai_temperature || 0.7;

            console.log("Settings loaded:", settings);
        }
    } catch (error) {
        console.error("Error loading settings:", error);
    }
}

function openSettings() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.classList.add('active');
}

function closeSettings() {
    const modal = document.getElementById('settings-modal');
    if (modal) modal.classList.remove('active');
}

async function saveSettings() {
    // Support both old and new IDs
    const usernameInput = document.getElementById('setting-username') || document.getElementById('settings-username');
    const themeInput = document.getElementById('setting-theme');
    const voiceInput = document.getElementById('setting-voice');
    const tempInput = document.getElementById('settings-temp');

    if (!usernameInput || !tempInput) {
        showToast("Settings form elements not found", "error");
        return;
    }

    const username = usernameInput.value.trim();
    const theme = themeInput ? themeInput.value : 'dark';
    const voice = voiceInput ? voiceInput.value : 'enabled';
    const temp = parseFloat(tempInput.value);

    if (!username) {
        showToast("Username is required", "error");
        return;
    }

    try {
        const response = await fetch(`${API_URL}/settings`, {
            method: 'PUT',  // Fixed: Use PUT instead of POST
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: username,
                theme: theme,
                ai_temperature: temp
            })
        });

        if (response.ok) {
            showToast("Settings saved!");
            closeSettings();
            // Reload to apply changes (e.g. username in chat)
            location.reload();
        } else {
            showToast("Failed to save settings", "error");
        }
    } catch (error) {
        console.error("Error saving settings:", error);
        showToast("Error saving settings", "error");
    }
}

// Helper for Toasts (assuming main.js has showToast, but defining here just in case or relying on main.js)
// We will assume main.js provides showToast.
