// Settings functionality - WITH PERSISTENCE

function loadSettings() {
    // Load and APPLY theme
    const theme = localStorage.getItem('aura-theme') || 'dark';
    const themeSelect = document.getElementById('theme-select');
    if (themeSelect) {
        themeSelect.value = theme;
    }
    applyTheme(theme);

    // Load temperature
    const temp = localStorage.getItem('aura-temperature') || '10';
    const tempSlider = document.getElementById('temperature-slider');
    const tempValue = document.getElementById('temp-value');
    if (tempSlider && tempValue) {
        tempSlider.value = temp;
        tempValue.textContent = (parseInt(temp) / 100).toFixed(1);
    }

    // Load and APPLY user name
    const userName = localStorage.getItem('aura-username') || 'Rakshak';
    const userNameInput = document.getElementById('user-name');
    if (userNameInput) {
        userNameInput.value = userName;
    }

    // Apply username to UI elements NOW
    updateUserNameInUI(userName);
}

function updateUserNameInUI(name) {
    // Update all name displays
    document.querySelectorAll('.user-info .name').forEach(el => {
        el.textContent = name;
    });

    // Update welcome message
    const welcomeName = document.getElementById('welcome-name');
    if (welcomeName) {
        welcomeName.textContent = name;
    }

    // Update all avatars
    const initial = name.charAt(0).toUpperCase();
    document.querySelectorAll('.user-profile .avatar').forEach(el => {
        el.textContent = initial;
    });
}

function saveSettings() {
    // Save theme
    const themeSelect = document.getElementById('theme-select');
    if (themeSelect) {
        const theme = themeSelect.value;
        localStorage.setItem('aura-theme', theme);
        applyTheme(theme);
    }

    // Save temperature
    const tempSlider = document.getElementById('temperature-slider');
    if (tempSlider) {
        localStorage.setItem('aura-temperature', tempSlider.value);
    }

    // Save and apply username
    const userNameInput = document.getElementById('user-name');
    if (userNameInput) {
        const newName = userNameInput.value.trim() || 'User';
        localStorage.setItem('aura-username', newName);
        updateUserNameInUI(newName);
    }

    showToast('Settings saved!');
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
