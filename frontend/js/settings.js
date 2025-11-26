// Settings functionality - WITH PERSISTENCE

async function loadSettings() {
    try {
        // Fetch from backend
        const response = await fetch('/api/settings');
        if (response.ok) {
            const settings = await response.json();

            // Apply Theme
            const theme = settings.theme || 'dark';
            const themeSelect = document.getElementById('theme-select');
            if (themeSelect) themeSelect.value = theme;
            applyTheme(theme);

            // Apply Username
            const userName = settings.username || 'User';
            const userNameInput = document.getElementById('user-name');
            if (userNameInput) userNameInput.value = userName;
            updateUserNameInUI(userName);

            // Apply Temperature
            const temp = settings.ai_temperature || 0.7; // Backend uses 0-1 float
            const tempSlider = document.getElementById('temperature-slider');
            const tempValue = document.getElementById('temp-value');
            if (tempSlider && tempValue) {
                tempSlider.value = temp;
                tempValue.textContent = temp;
            }

            // Save to local storage as backup/cache
            localStorage.setItem('aura-theme', theme);
            localStorage.setItem('aura-username', userName);
        }
    } catch (error) {
        console.error('Failed to load settings from backend:', error);
        // Fallback to local storage
        const theme = localStorage.getItem('aura-theme') || 'dark';
        applyTheme(theme);
    }
}

async function saveSettings() {
    const theme = document.getElementById('theme-select')?.value || 'dark';
    const username = document.getElementById('user-name')?.value || 'User';
    const temp = parseFloat(document.getElementById('temperature-slider')?.value || 0.7);

    const data = {
        theme,
        username,
        ai_temperature: temp
    };

    try {
        const response = await fetch('/api/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            showToast('Settings saved!');

            // Update UI immediately
            applyTheme(theme);
            updateUserNameInUI(username);

            // Update Local Storage
            localStorage.setItem('aura-theme', theme);
            localStorage.setItem('aura-username', username);
        } else {
            showToast('Failed to save settings', 'error');
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        showToast('Error saving settings', 'error');
    }
}

function applyTheme(theme) {
    if (theme === 'light') {
        document.body.classList.add('light-mode');
    } else {
        document.body.classList.remove('light-mode');
    }
}

function openSettings() {
    const modal = document.getElementById('settings-modal');
    if (modal) {
        modal.classList.add('active');
        loadSettings();
    }
}

function closeSettings() {
    const modal = document.getElementById('settings-modal');
    if (modal) {
        modal.classList.remove('active');
    }
}

async function exportData() {
    try {
        showToast('Preparing data export...', 'info');

        const response = await fetch('/api/export');
        if (!response.ok) throw new Error('Export failed');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `aura-export-${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showToast('✅ Data exported successfully!');
    } catch (error) {
        console.error('Export error:', error);
        showToast('Failed to export data', 'error');
    }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    const tempSlider = document.getElementById('temperature-slider');
    const tempValue = document.getElementById('temp-value');

    if (tempSlider && tempValue) {
        tempSlider.addEventListener('input', (e) => {
            tempValue.textContent = (parseInt(e.target.value) / 100).toFixed(1);
        });

        tempSlider.addEventListener('change', saveSettings);
    }

    // Auto-save on change
    const themeSelect = document.getElementById('theme-select');
    if (themeSelect) {
        themeSelect.addEventListener('change', saveSettings);
    }

    const userNameInput = document.getElementById('user-name');
    if (userNameInput) {
        userNameInput.addEventListener('blur', saveSettings);
    }
});
