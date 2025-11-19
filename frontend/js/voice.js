let recognition;

function activateVoice() {
    if ('webkitSpeechRecognition' in window) {
        recognition = new webkitSpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.lang = 'en-US';
        
        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript.toLowerCase();
            if (transcript.includes('hey aura')) {
                recognition.stop();
                const cmd = transcript.replace('hey aura', '').trim();
                if (cmd) {
                    document.getElementById('chat-input').value = cmd;
                    sendMessage({key: 'Enter'});
                }
            }
        };
        recognition.start();
    } else {
        alert('Voice not supported; upload audio for STT.');
    }
}

// TTS stub: Use Web Speech Synthesis
function speak(text) {
    const utterance = new SpeechSynthesisUtterance(text);
    speechSynthesis.speak(utterance);
}