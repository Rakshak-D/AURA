// Voice input functionality
let recognition = null;
let isListening = false;

function setupVoiceInput() {
    const voiceBtn = document.getElementById('voice-btn');
    
    // Check if browser supports speech recognition
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';
        
        recognition.onstart = () => {
            isListening = true;
            document.getElementById('voice-indicator').style.display = 'flex';
            voiceBtn.classList.add('listening');
        };
        
        recognition.onresult = (event) => {
            const transcript = event.results.transcript;
            document.getElementById('chat-input').value = transcript;
            stopVoiceInput();
            
            // Auto-send if user said something
            if (transcript.trim()) {
                setTimeout(() => sendMessage(), 500);
            }
        };
        
        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            stopVoiceInput();
            
            if (event.error === 'no-speech') {
                showToast('No speech detected. Please try again.', 'warning');
            } else {
                showToast('Voice input error. Please try again.', 'error');
            }
        };
        
        recognition.onend = () => {
            stopVoiceInput();
        };
        
        voiceBtn.addEventListener('click', toggleVoiceInput);
    } else {
        voiceBtn.style.display = 'none';
        console.warn('Speech recognition not supported');
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
        recognition.start();
    }
}

function stopVoiceInput() {
    if (recognition && isListening) {
        recognition.stop();
        isListening = false;
        document.getElementById('voice-indicator').style.display = 'none';
        document.getElementById('voice-btn').classList.remove('listening');
    }
}
