// Analytics Logic
let activityChart = null;
let distributionChart = null;

// Dark mode chart colors
const chartColors = {
    text: '#F3F4F6',
    grid: 'rgba(255, 255, 255, 0.1)',
    primary: '#3B82F6',
    primaryLight: 'rgba(59, 130, 246, 0.1)',
    success: '#10B981',
    warning: '#F59E0B',
    danger: '#EF4444',
    muted: '#6B7280'
};

async function loadAnalytics() {
    try {
        const apiUrl = typeof API_URL !== 'undefined' ? API_URL : '/api';
        
        // 1. Fetch Focus Score
        const scoreData = await apiJson(`${apiUrl}/insights/focus-score`);

        renderFocusScore(scoreData);

        // 2. Fetch Trends
        const trendsData = await apiJson(`${apiUrl}/insights/trends`);

        renderCharts(trendsData);

    } catch (error) {
        console.error('Error loading analytics:', error);
        activityChart?.destroy();
        distributionChart?.destroy();
        activityChart = null;
        distributionChart = null;
        if (typeof showToast === 'function') {
            showToast('Failed to load analytics', 'error');
        }
        document.getElementById('focus-score')?.replaceChildren(AuraSafe.element('span', 'error-state', 'Unavailable'));
    }
}
function renderFocusScore(data) {
    const scoreEl = document.getElementById('focus-score');
    const labelEl = document.getElementById('focus-score-label');
    const trendEl = document.getElementById('focus-score-trend');

    if (scoreEl) {
        scoreEl.textContent = data.score ?? '--';
    }
    
    if (labelEl) {
        labelEl.textContent = data.label || 'No Data';
    }
    
    if (trendEl) {
        if (data.trend_text) {
            trendEl.textContent = data.trend_text;
            // Add class based on trend
            trendEl.className = 'focus-score-trend';
            if (data.trend && data.trend > 0) {
                trendEl.classList.add('positive');
            } else if (data.trend && data.trend < 0) {
                trendEl.classList.add('negative');
            }
        } else {
            trendEl.textContent = '';
        }
    }
}

function renderCharts(data) {
    // Activity Chart (Line)
    const activityCtx = document.getElementById('activityChart');
    if (activityCtx) {
        if (activityChart) activityChart.destroy();

        activityChart = new Chart(activityCtx, {
            type: 'line',
            data: data.activity,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { 
                        display: false 
                    },
                    tooltip: {
                        backgroundColor: 'rgba(21, 27, 43, 0.95)',
                        titleColor: chartColors.text,
                        bodyColor: chartColors.text,
                        borderColor: chartColors.primary,
                        borderWidth: 1,
                        padding: 12
                    }
                },
                scales: {
                    y: { 
                        beginAtZero: true,
                        grid: { 
                            color: chartColors.grid,
                            drawBorder: false
                        },
                        ticks: {
                            color: chartColors.text,
                            font: {
                                size: 11
                            }
                        }
                    },
                    x: { 
                        grid: { 
                            display: false,
                            drawBorder: false
                        },
                        ticks: {
                            color: chartColors.text,
                            font: {
                                size: 11
                            }
                        }
                    }
                }
            }
        });
    }

    // Distribution Chart (Doughnut)
    const priorityCtx = document.getElementById('priorityChart');
    if (priorityCtx) {
        if (distributionChart) distributionChart.destroy();

        distributionChart = new Chart(priorityCtx, {
            type: 'doughnut',
            data: data.distribution,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { 
                        position: 'right',
                        labels: { 
                            color: chartColors.text,
                            font: {
                                size: 12
                            },
                            padding: 15,
                            usePointStyle: true
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(21, 27, 43, 0.95)',
                        titleColor: chartColors.text,
                        bodyColor: chartColors.text,
                        borderColor: chartColors.primary,
                        borderWidth: 1,
                        padding: 12
                    }
                },
                cutout: '70%'
            }
        });
    }
}

