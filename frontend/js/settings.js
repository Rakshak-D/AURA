// Settings Management (Dark mode only)

// API_URL is defined in main.js

document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
});

// Dark mode is permanent now; keep this for backwards compatibility.
function applyTheme() {
    // no-op
}

async function loadSettings() {
    try {
        const settings = await apiJson(`${API_URL}/settings`);
        const usernameInput = document.getElementById('setting-username') || document.getElementById('settings-username');
        const themeInput = document.getElementById('setting-theme');
        const tempInput = document.getElementById('settings-temp');
        if (usernameInput && settings?.username != null) usernameInput.value = settings.username;
        if (themeInput && settings?.theme != null) themeInput.value = settings.theme;
        if (tempInput && settings?.ai_temperature != null) tempInput.value = settings.ai_temperature;
    } catch (error) {
        showToast(error.message || 'Failed to load settings', 'error');
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
    const tempInput = document.getElementById('settings-temp');

    if (!usernameInput || !tempInput) {
        if (typeof showToast === 'function') {
            showToast("Settings form elements not found", "error");
        }
        return;
    }

    const username = usernameInput.value.trim();
    const theme = themeInput?.value;
    const temp = parseFloat(tempInput.value);

    if (!username) {
        if (typeof showToast === 'function') {
            showToast("Username is required", "error");
        }
        return;
    }

    try {
        const settings = await apiJson(`${API_URL}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: username,
                ...(theme ? { theme } : {}),
                ai_temperature: temp
            })
        });

        const usernameValue = settings?.username ?? username;
        if (usernameInput) usernameInput.value = usernameValue;
        if (tempInput && settings?.ai_temperature != null) tempInput.value = settings.ai_temperature;
        showToast("Settings saved!");
        closeSettings();
    } catch (error) {
        console.error("Error saving settings:", error);
        if (typeof showToast === 'function') {
            showToast("Error saving settings", "error");
        }
    }
}
