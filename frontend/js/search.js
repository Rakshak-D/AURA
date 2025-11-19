document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.querySelector('#search-bar input');
    searchInput.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') {
            const query = e.target.value;
            // Global search: Query RAG or DB
            const res = await fetch('/api/chat', {  // Reuse chat for search
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: `Search: ${query}`})
            });
            const data = await res.json();
            alert(data.response);  // Or populate results
        }
    });
});