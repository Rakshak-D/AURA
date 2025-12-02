// Settings Management (Dark mode only)

// API_URL is defined in main.js

// Load settings on window load (ensures all elements exist)
window.addEventListener('load', loadSettings);
document.addEventListener('DOMContentLoaded', loadSettings);

// Dark mode is permanent now; keep this for backwards compatibility.
function applyTheme() {
    // no-op
}

async function loadSettings() {
    try {
        const response = await fetch(`${API_URL}/settings`);
        if (response.ok) {
            const settings = await response.json();

            // Populate Modal Inputs - support both old and new IDs
            const usernameInput = document.getElementById('setting-username') || document.getElementById('settings-username');
            const voiceInput = document.getElementById('setting-voice');
            const tempInput = document.getElementById('settings-temp');

            if (usernameInput) usernameInput.value = settings.username || 'User';
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
    const voiceInput = document.getElementById('setting-voice');
    const tempInput = document.getElementById('settings-temp');

    if (!usernameInput || !tempInput) {
        if (typeof showToast === 'function') {
            showToast("Settings form elements not found", "error");
        }
        return;
    }

    const username = usernameInput.value.trim();
    const theme = 'dark';
    const voice = voiceInput ? voiceInput.value : 'enabled';
    const temp = parseFloat(tempInput.value);

    if (!username) {
        if (typeof showToast === 'function') {
            showToast("Username is required", "error");
        }
        return;
    }

    try {
        const response = await fetch(`${API_URL}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: username,
                theme: theme,
                ai_temperature: temp
            })
        });

        if (response.ok) {
            if (typeof showToast === 'function') {
                showToast("Settings saved!");
            }
            closeSettings();
        } else {
            if (typeof showToast === 'function') {
                showToast("Failed to save settings", "error");
            }
        }
    } catch (error) {
        console.error("Error saving settings:", error);
        if (typeof showToast === 'function') {
            showToast("Error saving settings", "error");
        }
    }
}
