// Voice input functionality with proper error handling

let recognition = null;
let isListening = false;

function setupVoiceInput() {
    const voiceBtn = document.getElementById('voice-btn');

    if (!voiceBtn) {
        console.warn('Voice button not found');
        return;
    }

    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();

        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';

        recognition.onstart = () => {
            isListening = true;
            voiceBtn.classList.add('listening');
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            const chatInput = document.getElementById('chat-input');
            if (chatInput) {
                chatInput.value = transcript;
                chatInput.focus();
            }
            stopVoiceInput();

            // Auto-send after a brief delay
            if (transcript.trim()) {
                setTimeout(() => sendMessage(), 300);
            }
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            stopVoiceInput();

            if (event.error === 'no-speech') {
                showToast('No speech detected. Try again.', 'info');
            } else if (event.error === 'not-allowed') {
                showToast('Microphone access denied', 'error');
            } else {
                showToast('Voice input error', 'error');
            }
        };

        recognition.onend = () => {
            stopVoiceInput();
        };

        voiceBtn.addEventListener('click', toggleVoiceInput);
    } else {
        voiceBtn.style.display = 'none';
        console.warn('Speech recognition not supported in this browser');
    }
}

function toggleVoiceInput() {
    if (isListening) {
        stopVoiceInput();
    } else {
        startVoiceInput();
    }
}

function startVoiceInput() {
    if (recognition && !isListening) {
        try {
            recognition.start();
        } catch (error) {
            console.error('Failed to start recognition:', error);
            showToast('Could not start voice input', 'error');
        }
    }
}

function stopVoiceInput() {
    if (recognition && isListening) {
        try {
            recognition.stop();
        } catch (error) {
            console.error('Error stopping recognition:', error);
        }
        isListening = false;
        const voiceBtn = document.getElementById('voice-btn');
        if (voiceBtn) {
            voiceBtn.classList.remove('listening');
        }
    }
}
