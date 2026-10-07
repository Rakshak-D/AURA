// Browser-only voice input. The backend never receives audio.
let auraRecognition = null;
let auraVoiceActive = false;

function setupVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const voiceButton = document.querySelector('.icon-btn i[data-lucide="mic"]')?.parentElement;
    if (!SpeechRecognition) {
        if (voiceButton) voiceButton.style.display = 'none';
        return;
    }
    if (!voiceButton || auraRecognition) return;
    auraRecognition = new SpeechRecognition();
    auraRecognition.continuous = false;
    auraRecognition.interimResults = false;
    auraRecognition.lang = 'en-US';
    auraRecognition.onstart = () => {
        auraVoiceActive = true;
        voiceButton.classList.add('listening');
    };
    auraRecognition.onresult = (event) => {
        const transcript = event.results?.[0]?.[0]?.transcript || '';
        const input = document.getElementById('chat-input');
        if (input) {
            input.value = transcript;
            input.focus();
        }
        stopVoiceInput();
        if (transcript.trim()) setTimeout(() => sendMessage(), 300);
    };
    auraRecognition.onerror = (event) => {
        stopVoiceInput();
        showToast(event.error === 'not-allowed' ? 'Microphone access denied' : 'Voice input error', 'error');
    };
    auraRecognition.onend = () => stopVoiceInput();
}

function toggleVoice() {
    if (!auraRecognition) return showToast('Voice is not supported in this browser', 'error');
    if (auraVoiceActive) stopVoiceInput();
    else startVoiceInput();
}

function startVoiceInput() {
    if (!auraRecognition || auraVoiceActive) return;
    try { auraRecognition.start(); }
    catch (error) { showToast('Could not start voice input', 'error'); }
}

function stopVoiceInput() {
    if (auraRecognition && auraVoiceActive) {
        try { auraRecognition.stop(); } catch (error) { /* already stopped */ }
    }
    auraVoiceActive = false;
    document.querySelector('.icon-btn i[data-lucide="mic"]')?.parentElement.classList.remove('listening');
}

window.addEventListener('beforeunload', stopVoiceInput);
