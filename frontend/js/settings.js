// Settings Management

// Settings Management

// API_URL is defined in main.js

// Load settings on startup
document.addEventListener('DOMContentLoaded', loadSettings);

async function loadSettings() {
    try {
        const response = await fetch(`${API_URL}/settings`);
        if (response.ok) {
            const settings = await response.json();

            // Apply Theme
            // (Currently theme is CSS-based, but we could toggle classes if needed)

            // Populate Modal Inputs
            const usernameInput = document.getElementById('settings-username');
            const tempInput = document.getElementById('settings-temp');

            if (usernameInput) usernameInput.value = settings.username || 'User';
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
    const username = document.getElementById('settings-username').value;
    const temp = parseFloat(document.getElementById('settings-temp').value);

    try {
        const response = await fetch(`${API_URL}/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: username,
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
