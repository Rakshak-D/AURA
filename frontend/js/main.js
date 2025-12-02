// Main Application Logic

// Global Configuration
const API_URL = '/api';

// Global State
let isVoiceActive = false;
let recognition = null;

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Lucide Icons
    lucide.createIcons();

    // Default View
    switchView('chat');

    // Initialize Voice
    setupVoice();
});

// View Switching
function switchView(viewId) {
    // Hide all views
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));

    // Show selected view
    const target = document.getElementById(`view-${viewId}`);
    if (target) target.classList.add('active');

    // Update Sidebar Active State
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    // Find button that calls this view
    const btn = document.querySelector(`button[onclick="switchView('${viewId}')"]`);
    if (btn) btn.classList.add('active');

    // Close sidebar on mobile after selection
    if (window.innerWidth <= 768) {
        document.getElementById('sidebar').classList.remove('open');
    }

    // Trigger view-specific initialization
    if (viewId === 'calendar') {
        // Wait a bit for DOM to be ready, then render
        setTimeout(() => {
            console.log('Switching to calendar view, initializing...');
            // Force update date header
            if (typeof updateDateHeader === 'function') {
                updateDateHeader();
            }
            // Render calendar
            if (typeof renderCalendar === 'function') {
                console.log('Calling renderCalendar()');
                renderCalendar();
            } else {
                console.warn('renderCalendar function not found');
            }
        }, 200);
    } else if (viewId === 'tasks' && typeof loadTasks === 'function') {
        setTimeout(() => loadTasks(), 100);
    }
}

// Sidebar Toggle (Mobile)
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('open');
}

// Toast Notifications
function showToast(message, type = 'success') {
    // Create toast element
    const toast = document.createElement('div');
    toast.style.position = 'fixed';
    toast.style.bottom = '20px';
    toast.style.right = '20px';
    toast.style.padding = '1rem 1.5rem';
    toast.style.borderRadius = '8px';
    toast.style.color = 'white';
    toast.style.fontWeight = '500';
    toast.style.zIndex = '1000';
    toast.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
    toast.style.animation = 'slideIn 0.3s ease';

    if (type === 'error') {
        toast.style.background = '#EF4444';
    } else {
        toast.style.background = '#10B981';
    }

    toast.textContent = message;
    document.body.appendChild(toast);

    // Remove after 3s
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Voice Recognition
function setupVoice() {
    if ('webkitSpeechRecognition' in window) {
        recognition = new webkitSpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;

        recognition.onresult = (event) => {
            const text = event.results[0][0].transcript;
            document.getElementById('chat-input').value = text;
            sendMessage(); // Auto-send
        };

        recognition.onend = () => {
            isVoiceActive = false;
            updateVoiceIcon();
        };

        recognition.onerror = (event) => {
            console.error("Voice error:", event.error);
            isVoiceActive = false;
            updateVoiceIcon();
            showToast("Voice recognition error", "error");
        };
    } else {
        console.warn("Web Speech API not supported");
    }
}

function toggleVoice() {
    if (!recognition) return showToast("Voice not supported", "error");

    if (isVoiceActive) {
        recognition.stop();
    } else {
        recognition.start();
        isVoiceActive = true;
    }
    updateVoiceIcon();
}

function updateVoiceIcon() {
    const btn = document.querySelector('.icon-btn i[data-lucide="mic"]');
    if (btn) {
        if (isVoiceActive) {
            btn.parentElement.style.color = '#EF4444';
            btn.parentElement.classList.add('pulse');
        } else {
            btn.parentElement.style.color = '';
            btn.parentElement.classList.remove('pulse');
        }
    }
}

// Global API Call Helper
async function apiCall(endpoint, method = 'GET', body = null) {
    try {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };
        if (body) options.body = JSON.stringify(body);

        const response = await fetch(`${API_URL}${endpoint}`, options);
        return await response.json();
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        showToast("Connection error", "error");
        return null;
    }
}
