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
        const result = await apiJson(`${apiUrl}/upload`, {
            method: 'POST',
            body: formData
        });
        if (typeof showToast === 'function') {
            showToast(`✅ ${result?.message || `${file.name} uploaded successfully!`}`, 'success');
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

    AuraSafe.clear(filesList).appendChild(AuraSafe.element('div', 'loading', 'Loading...'));

    try {
        const data = await apiJson(`${API_URL}/upload/files`);
        const files = Array.isArray(data?.data?.files) ? data.data.files : [];
        if (!data || !Array.isArray(data.data?.files)) throw new Error('Invalid file-list response');

        AuraSafe.clear(filesList);
        if (!files || files.length === 0) {
            const empty = AuraSafe.element('div', null, 'No documents yet. Upload some files to build your knowledge base!');
            empty.style.cssText = 'text-align:center;padding:2rem;color:var(--text-muted)';
            filesList.appendChild(empty);
            return;
        }

        files.forEach(file => {
            const div = document.createElement('div');
            div.className = 'file-item';
            div.style.cssText = 'padding: 1rem; margin-bottom: 0.5rem; background: var(--surface-color); border-radius: var(--radius-md); display: flex; align-items: center; gap: 0.75rem;';
            const icon = AuraSafe.element('span', null, '📄');
            icon.style.fontSize = '1.5rem';
            const name = AuraSafe.element('span', null, file.filename || file.name || 'Unknown file');
            name.style.cssText = 'flex:1;color:var(--text-primary)';
            const deleteButton = AuraSafe.element('button', 'icon-btn kb-delete-btn');
            deleteButton.type = 'button';
            deleteButton.title = 'Delete document';
            deleteButton.addEventListener('click', () => deleteDocument(file.id));
            deleteButton.appendChild(AuraSafe.element('span', null, 'Delete'));
            div.append(icon, name, deleteButton);
            filesList.appendChild(div);
        });

        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    } catch (error) {
        console.error('Error loading files:', error);
        const errorState = AuraSafe.element('div', null, 'Failed to load files');
        errorState.style.cssText = 'text-align:center;padding:2rem;color:var(--danger)';
        AuraSafe.clear(filesList).appendChild(errorState);
    }
}

async function deleteDocument(docId) {
    if (!confirm('Are you sure you want to delete this document from your knowledge base?')) {
        return;
    }

    try {
        const result = await apiJson(`${API_URL}/upload/${docId}`, { method: 'DELETE' });

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
