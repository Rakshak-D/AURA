// File upload functionality
function setupFileUpload() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    
    // Drag and drop handlers
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        handleFiles(files);
    });
}

function handleFileSelect(event) {
    const files = event.target.files;
    handleFiles(files);
}

async function handleFiles(files) {
    for (let file of files) {
        await uploadFile(file);
    }
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        showToast(`Uploading ${file.name}...`, 'info');
        
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('Upload failed');
        }
        
        const result = await response.json();
        showToast(`✅ ${file.name} uploaded successfully!`);
        
        // Refresh uploaded files list
        loadUploadedFiles();
        
    } catch (error) {
        console.error('Upload error:', error);
        showToast(`Failed to upload ${file.name}`, 'error');
    }
}

async function loadUploadedFiles() {
    // This would fetch the list of uploaded files from the server
    // For now, just show a placeholder
    const filesList = document.getElementById('files-list');
    filesList.innerHTML = '<div class="loading">Loading files...</div>';
    
    // TODO: Implement API endpoint to list uploaded files
}
