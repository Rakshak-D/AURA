// Global Search Functionality

async function performGlobalSearch(query) {
    if (!query || query.trim() === '') return;

    const modal = document.getElementById('search-modal');
    const resultsContainer = document.getElementById('search-results');

    // Safe check - search modal is optional feature
    if (!modal || !resultsContainer) {
        console.warn('Search modal elements not found. Search feature may not be fully implemented.');
        return;
    }

    modal.style.display = 'flex';
    AuraSafe.clear(resultsContainer).appendChild(AuraSafe.element('div', 'loading', 'Searching...'));

    try {
        const response = await apiFetch(`${API_URL}/search?q=${encodeURIComponent(query)}`);
        const data = await response.json();

        if (Array.isArray(data.results) && data.results.length > 0) {
            AuraSafe.clear(resultsContainer);
            data.results.forEach((item) => {
                const result = AuraSafe.element('div', 'search-result-item');
                result.addEventListener('click', () => handleResultClick(item.type, item.id));
                result.appendChild(AuraSafe.element('div', 'result-icon', getResultIcon(item.type)));
                const content = AuraSafe.element('div', 'result-content');
                content.appendChild(AuraSafe.element('div', 'result-title', item.title));
                content.appendChild(AuraSafe.element('div', 'result-snippet', item.snippet));
                content.appendChild(AuraSafe.element('div', 'result-meta', `${item.type || ''} • ${item.date || ''}`));
                result.appendChild(content);
                resultsContainer.appendChild(result);
            });
        } else {
            AuraSafe.clear(resultsContainer).appendChild(AuraSafe.element('div', 'no-results', 'No results found'));
        }

    } catch (error) {
        console.error('Search error:', error);
        AuraSafe.clear(resultsContainer).appendChild(AuraSafe.element('div', 'error', 'Search failed'));
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
    const modal = document.getElementById('search-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}
