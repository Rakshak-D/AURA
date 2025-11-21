let recognition;
let isListening = false;

function toggleVoice() {
    const btn = document.getElementById('voice-btn');
    
    if (!('webkitSpeechRecognition' in window)) {
        alert("Voice not supported in this browser.");
        return;
    }

    if (isListening) {
        recognition.stop();
        isListening = false;
        btn.classList.remove('text-red-500', 'animate-pulse');
        btn.classList.add('text-gray-400');
        return;
    }

    recognition = new webkitSpeechRecognition();
    recognition.continuous = false; // Better for commands
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
        isListening = true;
        btn.classList.remove('text-gray-400');
        btn.classList.add('text-red-500', 'animate-pulse');
    };

    recognition.onend = () => {
        isListening = false;
        btn.classList.remove('text-red-500', 'animate-pulse');
        btn.classList.add('text-gray-400');
    };

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript.toLowerCase();
        
        // Check for wake word OR direct command since button was pressed
        let command = transcript;
        if (transcript.includes('hey aura')) {
            command = transcript.replace('hey aura', '').trim();
        }
        
        if (command) {
            document.getElementById('chat-input').value = command;
            sendMessage();
        }
    };

    recognition.start();
}