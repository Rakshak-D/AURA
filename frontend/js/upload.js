// File upload functionality
function setupFileUpload() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-upload');
    const uploadBtn = document.getElementById('upload-btn');

    // Initial load
    loadUploadedFiles();

    // Click listener for upload button
    if (uploadBtn && fileInput) {
        uploadBtn.addEventListener('click', () => {
            fileInput.click();
        });
    }

    // File input change handler
    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            const files = e.target.files;
            if (files && files.length > 0) {
                handleFiles(files);
            }
        });
    }

    // Drag and drop handlers
    if (dropZone) {
        dropZone.addEventListener('click', () => {
            if (fileInput) fileInput.click();
        });

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
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    setupFileUpload();
});

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
        if (typeof showToast === 'function') {
            showToast(`Uploading ${file.name}...`, 'info');
        }

        const apiUrl = typeof API_URL !== 'undefined' ? API_URL : '/api';
        const response = await fetch(`${apiUrl}/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(errorData.detail || 'Upload failed');
        }

        const result = await response.json();
        if (typeof showToast === 'function') {
            showToast(`✅ ${file.name} uploaded successfully!`, 'success');
        } else {
            alert(`✅ ${file.name} uploaded successfully!`);
        }

        loadUploadedFiles();

    } catch (error) {
        console.error('Upload error:', error);
        if (typeof showToast === 'function') {
            showToast(`Failed to upload ${file.name}: ${error.message}`, 'error');
        } else {
            alert(`Failed to upload ${file.name}: ${error.message}`);
        }
    }
}

async function loadUploadedFiles() {
    const filesList = document.getElementById('file-list');
    if (!filesList) return;

    filesList.innerHTML = '<div class="loading">Loading...</div>';

    try {
        const response = await fetch(`${API_URL}/upload/files`);
        if (!response.ok) {
            throw new Error('Failed to fetch files');
        }
        
        const data = await response.json();

        // Support both legacy shape { files: [] } and new envelope { success, data: { files: [] } }
        const files = (data && Array.isArray(data.files))
            ? data.files
            : (data && data.data && Array.isArray(data.data.files))
                ? data.data.files
                : [];

        filesList.innerHTML = '';
        if (!files || files.length === 0) {
            filesList.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--text-muted);">No documents yet. Upload some files to build your knowledge base!</div>';
            return;
        }

        files.forEach(file => {
            const div = document.createElement('div');
            div.className = 'file-item';
            div.style.cssText = 'padding: 1rem; margin-bottom: 0.5rem; background: var(--surface-color); border-radius: var(--radius-md); display: flex; align-items: center; gap: 0.75rem;';
            div.innerHTML = `
                <span style="font-size: 1.5rem;">📄</span>
                <span style="flex: 1; color: var(--text-primary);">${file.filename || file.name || 'Unknown file'}</span>
                <button class="icon-btn kb-delete-btn" title="Delete document" onclick="deleteDocument(${file.id})">
                    <i data-lucide="trash-2"></i>
                </button>
            `;
            filesList.appendChild(div);
        });

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    } catch (error) {
        console.error('Error loading files:', error);
        filesList.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--danger);">Failed to load files</div>';
    }
}

async function deleteDocument(docId) {
    if (!confirm('Are you sure you want to delete this document from your knowledge base?')) {
        return;
    }

    try {
        const response = await fetch(`${API_URL}/upload/${docId}`, {
            method: 'DELETE'
        });

        const result = await response.json().catch(() => null);

        if (!response.ok || (result && result.success === false)) {
            const message =
                (result && (result.message || (result.error && result.error.message))) ||
                'Failed to delete document';
            if (typeof showToast === 'function') {
                showToast(message, 'error');
            } else {
                alert(message);
            }
            return;
        }

        if (typeof showToast === 'function') {
            showToast('Document deleted', 'success');
        }

        // Refresh the list
        loadUploadedFiles();
    } catch (error) {
        console.error('Error deleting document:', error);
        if (typeof showToast === 'function') {
            showToast('Error deleting document', 'error');
        }
    }
}
