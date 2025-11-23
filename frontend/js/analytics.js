// Analytics & Charts Logic

async function loadAnalytics() {
    try {
        const analytics = await apiCall('/analytics?days=30');

        // Update Stats Cards
        animateValue('total-completed', analytics.total_completed || 0);
        document.getElementById('completion-rate').textContent = `${analytics.completion_rate || 0}%`;
        document.getElementById('daily-average').textContent = analytics.average_per_day?.toFixed(1) || 0;
        animateValue('total-created', analytics.total_created || 0);

        // Render Charts
        renderActivityChart(analytics.tasks_by_day);
        renderPriorityChart(analytics.priority_breakdown);

    } catch (error) {
        console.error('Error loading analytics:', error);
        showToast('Failed to load insights', 'error');
    }
}

function animateValue(id, end) {
    const obj = document.getElementById(id);
    if (!obj) return;

    const start = 0;
    const duration = 1000;
    let startTimestamp = null;

    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        obj.innerHTML = Math.floor(progress * (end - start) + start);
        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };
    window.requestAnimationFrame(step);
}

function renderActivityChart(data) {
    const container = document.getElementById('activity-chart');
    if (!container) return;

    // Convert data object to array and sort by date
    const days = Object.keys(data).sort().slice(-7); // Last 7 days
    const values = days.map(day => data[day]);
    const maxVal = Math.max(...values, 5); // Min max is 5

    const height = 200;
    const width = container.clientWidth || 600;
    const barWidth = 40;
    const gap = (width - (barWidth * days.length)) / (days.length + 1);

    let svgHtml = `<svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}">`;

    // Bars
    days.forEach((day, index) => {
        const val = data[day];
        const barHeight = (val / maxVal) * (height - 40);
        const x = gap + (index * (barWidth + gap));
        const y = height - barHeight - 20;

        // Bar
        svgHtml += `
            <rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="4" fill="url(#barGradient)" opacity="0.8">
                <animate attributeName="height" from="0" to="${barHeight}" dur="0.5s" fill="freeze" />
                <animate attributeName="y" from="${height - 20}" to="${y}" dur="0.5s" fill="freeze" />
            </rect>
        `;

        // Value Label
        if (val > 0) {
            svgHtml += `<text x="${x + barWidth / 2}" y="${y - 5}" text-anchor="middle" fill="var(--text-secondary)" font-size="12">${val}</text>`;
        }

        // Date Label
        const dateLabel = new Date(day).toLocaleDateString('en-US', { weekday: 'short' });
        svgHtml += `<text x="${x + barWidth / 2}" y="${height - 5}" text-anchor="middle" fill="var(--text-tertiary)" font-size="12">${dateLabel}</text>`;
    });

    // Gradient Definition
    svgHtml += `
        <defs>
            <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="var(--accent-primary)" />
                <stop offset="100%" stop-color="var(--accent-secondary)" />
            </linearGradient>
        </defs>
    `;

    svgHtml += '</svg>';
    container.innerHTML = svgHtml;
}

function renderPriorityChart(data) {
    const container = document.getElementById('priority-chart');
    if (!container) return;

    const total = Object.values(data).reduce((a, b) => a + b, 0);
    if (total === 0) {
        container.innerHTML = '<p style="text-align:center; color:var(--text-tertiary); padding-top: 80px;">No data available</p>';
        return;
    }

    const colors = {
        'urgent': '#ef4444',
        'high': '#f97316',
        'medium': '#3b82f6',
        'low': '#10b981'
    };

    let startAngle = 0;
    const radius = 80;
    const cx = 150;
    const cy = 100;

    let svgHtml = `<svg width="300" height="200" viewBox="0 0 300 200">`;
    let legendHtml = '<div style="display:flex; flex-direction:column; gap:8px; justify-content:center;">';

    Object.entries(data).forEach(([priority, count]) => {
        if (count === 0) return;

        const percentage = count / total;
        const angle = percentage * 2 * Math.PI;
        const endAngle = startAngle + angle;

        // Calculate path
        const x1 = cx + radius * Math.cos(startAngle);
        const y1 = cy + radius * Math.sin(startAngle);
        const x2 = cx + radius * Math.cos(endAngle);
        const y2 = cy + radius * Math.sin(endAngle);

        const largeArcFlag = percentage > 0.5 ? 1 : 0;

        // Donut slice
        const pathData = [
            `M ${cx} ${cy}`,
            `L ${x1} ${y1}`,
            `A ${radius} ${radius} 0 ${largeArcFlag} 1 ${x2} ${y2}`,
            `Z`
        ].join(' ');

        svgHtml += `<path d="${pathData}" fill="${colors[priority]}" stroke="var(--bg-secondary)" stroke-width="2" opacity="0.9"></path>`;

        startAngle = endAngle;

        // Legend
        legendHtml += `
            <div style="display:flex; align-items:center; gap:8px; font-size:12px; color:var(--text-secondary);">
                <span style="width:8px; height:8px; border-radius:50%; background:${colors[priority]}"></span>
                <span style="text-transform:capitalize;">${priority} (${count})</span>
            </div>
        `;
    });

    // Inner circle for donut
    svgHtml += `<circle cx="${cx}" cy="${cy}" r="${radius * 0.6}" fill="var(--bg-secondary)" />`;

    // Center Text
    svgHtml += `
        <text x="${cx}" y="${cy}" text-anchor="middle" dominant-baseline="middle" fill="var(--text-primary)" font-weight="bold" font-size="24">${total}</text>
        <text x="${cx}" y="${cy + 15}" text-anchor="middle" fill="var(--text-tertiary)" font-size="10">Tasks</text>
    `;

    svgHtml += '</svg>';
    legendHtml += '</div>';

    container.innerHTML = `<div style="display:flex; align-items:center; justify-content:center;">${svgHtml}${legendHtml}</div>`;
}
