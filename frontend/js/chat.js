async function sendMessage(event) {
    if (event.key === 'Enter') {
        const input = document.getElementById('chat-input');
        const msg = input.value;
        addMessage('User', msg);
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: msg})
        });
        const data = await res.json();
        addMessage('Aura', data.response);
        input.value = '';
    }
}

function addMessage(sender, msg) {
    const div = document.createElement('div');
    div.innerHTML = `<strong>${sender}:</strong> ${msg}`;
    document.getElementById('chat-messages').appendChild(div);
}