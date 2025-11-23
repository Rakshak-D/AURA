// Analytics Logic
let activityChart = null;
let distributionChart = null;

async function loadAnalytics() {
    try {
        // 1. Fetch Focus Score
        const scoreRes = await fetch('/api/insights/focus-score');
        const scoreData = await scoreRes.json();

        renderFocusScore(scoreData);

        // 2. Fetch Trends
        const trendsRes = await fetch('/api/insights/trends');
        const trendsData = await trendsRes.json();

        renderCharts(trendsData);

    } catch (error) {
        console.error('Error loading analytics:', error);
        showToast('Failed to load analytics', 'error');
    }
}

function renderFocusScore(data) {
    const scoreEl = document.getElementById('daily-average'); // Using existing ID for score
    const labelEl = document.getElementById('completion-rate'); // Using existing ID for label

    if (scoreEl) scoreEl.textContent = data.score;
    if (labelEl) labelEl.textContent = data.label;

    // Update other stats if available
    const totalCompleted = document.getElementById('total-completed');
    if (totalCompleted) totalCompleted.textContent = data.details.total_completed;
}

function renderCharts(data) {
    // Activity Chart (Line)
    const activityCtx = document.getElementById('activity-chart');
    if (activityCtx) {
        if (activityChart) activityChart.destroy();

        activityChart = new Chart(activityCtx, {
            type: 'line',
            data: data.activity,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(255, 255, 255, 0.1)' } },
                    x: { grid: { display: false } }
                }
            }
        });
    }

    // Distribution Chart (Doughnut)
    const priorityCtx = document.getElementById('priority-chart');
    if (priorityCtx) {
        if (distributionChart) distributionChart.destroy();

        distributionChart = new Chart(priorityCtx, {
            type: 'doughnut',
            data: data.distribution,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'right', labels: { color: '#fff' } }
                },
                cutout: '70%'
            }
        });
    }
}

// Initialize when view is active
document.addEventListener('DOMContentLoaded', () => {
    // If analytics view is active by default
    if (document.getElementById('analytics-view').classList.contains('active')) {
        loadAnalytics();
    }
});

// Listen for view changes
const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
        if (mutation.target.id === 'analytics-view' && mutation.target.classList.contains('active')) {
            loadAnalytics();
        }
    });
});

const analyticsView = document.getElementById('analytics-view');
if (analyticsView) {
    observer.observe(analyticsView, { attributes: true });
}
