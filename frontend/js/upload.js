// File upload functionality
function setupFileUpload() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');

    // Initial load
    loadUploadedFiles();

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
        showToast(`✅ ${file.name} uploaded!`);

        loadUploadedFiles();

    } catch (error) {
        console.error('Upload error:', error);
        showToast(`Failed to upload ${file.name}`, 'error');
    }
}

async function loadUploadedFiles() {
    const filesList = document.getElementById('files-list');
    filesList.innerHTML = '<div class="loading">Loading...</div>';

    try {
        const response = await fetch('/api/upload/files');
        const data = await response.json();

        if (data.status === 'success') {
            filesList.innerHTML = '';
            if (data.files.length === 0) {
                filesList.innerHTML = '<div class="no-files">No documents yet</div>';
                return;
            }

            data.files.forEach(file => {
                const div = document.createElement('div');
                div.className = 'file-item';
                div.innerHTML = `
                    <span class="file-icon">📄</span>
                    <span class="file-name">${file.filename}</span>
                `;
                filesList.appendChild(div);
            });
        }
    } catch (error) {
        console.error('Error loading files:', error);
        filesList.innerHTML = '<div class="error">Failed to load files</div>';
    }
}
