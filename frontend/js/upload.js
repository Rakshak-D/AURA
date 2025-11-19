function toggleUpload() {
    document.getElementById('upload-panel').classList.toggle('hidden');
}

async function handleUpload() {
    const file = document.getElementById('file-upload').files[0];
    const formData = new FormData();
    formData.append('file', file);
    formData.append('filename', file.name);
    
    const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
    });
    const data = await res.json();
    alert(`Uploaded: ${data.status}`);
}