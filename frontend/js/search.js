// Global Search Functionality

async function performGlobalSearch(query) {
    if (!query || query.trim() === '') return;

    const modal = document.getElementById('search-modal');
    const resultsContainer = document.getElementById('search-results');

    modal.style.display = 'flex';
    resultsContainer.innerHTML = '<div class="loading">Searching...</div>';

    try {
        const response = await fetch(`${API_URL}/search?q=${encodeURIComponent(query)}`);
        const data = await response.json();

        if (data.results && data.results.length > 0) {
            resultsContainer.innerHTML = data.results.map(item => `
                <div class="search-result-item" onclick="handleResultClick('${item.type}', '${item.id}')">
                    <div class="result-icon">${getResultIcon(item.type)}</div>
                    <div class="result-content">
                        <div class="result-title">${item.title}</div>
                        <div class="result-snippet">${item.snippet}</div>
                        <div class="result-meta">${item.type} • ${item.date}</div>
                    </div>
                </div>
            `).join('');
        } else {
            resultsContainer.innerHTML = '<div class="no-results">No results found</div>';
        }

    } catch (error) {
        console.error('Search error:', error);
        resultsContainer.innerHTML = '<div class="error">Search failed</div>';
    }
}

function getResultIcon(type) {
    switch (type) {
        case 'task': return '📝';
        case 'chat': return '💬';
        case 'document': return '📄';
        default: return '🔍';
    }
}

function handleResultClick(type, id) {
    closeSearchModal();
    if (type === 'task') {
        switchView('tasks');
        // Logic to highlight task could go here
    } else if (type === 'chat') {
        switchView('chat');
    } else if (type === 'document') {
        switchView('upload');
    }
}

function closeSearchModal() {
    document.getElementById('search-modal').style.display = 'none';
}
