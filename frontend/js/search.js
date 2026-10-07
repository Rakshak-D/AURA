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
        const data = await apiJson(`${API_URL}/search?q=${encodeURIComponent(query.trim())}`);
        if (!data || !Array.isArray(data.tasks) || !Array.isArray(data.knowledge)) {
            throw new Error('Invalid search response');
        }
        const groups = [
            ['Tasks', data.tasks, 'task'],
            ['Knowledge', data.knowledge, 'knowledge']
        ];
        const total = groups.reduce((count, group) => count + group[1].length, 0);
        AuraSafe.clear(resultsContainer);
        if (total > 0) {
            groups.forEach(([label, items, groupType]) => {
                if (!items.length) return;
                resultsContainer.appendChild(AuraSafe.element('h3', 'search-result-group', label));
                items.forEach((item) => {
                const result = AuraSafe.element('div', 'search-result-item');
                const type = item.type || groupType;
                if (item.id != null) result.addEventListener('click', () => handleResultClick(type, item.id));
                result.appendChild(AuraSafe.element('div', 'result-icon', getResultIcon(type)));
                const content = AuraSafe.element('div', 'result-content');
                content.appendChild(AuraSafe.element('div', 'result-title', item.title));
                content.appendChild(AuraSafe.element('div', 'result-snippet', item.snippet));
                content.appendChild(AuraSafe.element('div', 'result-meta', `${item.type || ''} • ${item.date || ''}`));
                result.appendChild(content);
                resultsContainer.appendChild(result);
                });
            });
        } else {
            resultsContainer.appendChild(AuraSafe.element('div', 'no-results', 'No results found'));
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
