// Calendar & Routine Logic

let currentCalendarDate = new Date();

async function renderCalendar() {
    const container = document.getElementById('calendar-grid');
    if (!container) return;

    const year = currentCalendarDate.getFullYear();
    const month = currentCalendarDate.getMonth();

    // Update Header
    const monthLabel = document.getElementById('current-month');
    if (monthLabel) {
        monthLabel.textContent = currentCalendarDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    }

    // Fetch Routine for this month (for now just fetching today's routine as a demo)
    // In a real app, we'd fetch the whole month's events
    const routine = await apiCall('/schedule/routine');
    const timeline = routine.timeline || [];

    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    let html = `
        <div class="calendar-controls">
            <h3>Your Schedule</h3>
            <button class="btn-primary" onclick="triggerAutoSchedule()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                </svg>
                Magic Schedule
            </button>
        </div>
        <div class="calendar-grid-inner">
    `;

    // Weekday headers
    ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].forEach(day => {
        html += `<div class="calendar-weekday">${day}</div>`;
    });

    // Empty cells
    for (let i = 0; i < firstDay; i++) {
        html += '<div class="calendar-day empty"></div>';
    }

    // Days
    const today = new Date();
    for (let day = 1; day <= daysInMonth; day++) {
        const isToday = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();

        let eventsHtml = '';
        if (isToday) {
            // Show first 3 events for today
            timeline.slice(0, 3).forEach(event => {
                let eventClass = 'event-dot';
                if (event.type === 'class') eventClass += ' event-class';
                if (event.type === 'task') eventClass += ' event-task';

                eventsHtml += `
                    <div class="${eventClass}">
                        • ${event.title}
                    </div>
                `;
            });
        }

        html += `
            <div class="calendar-day${isToday ? ' today' : ''}" onclick="showDayDetails(${day})">
                <div class="day-number">${day}</div>
                ${eventsHtml}
            </div>
        `;
    }

    html += '</div>';

    // Add Timeline View for Today
    html += `
        <div class="timeline-view">
            <h3>Today's Timeline</h3>
            <div class="timeline-list">
                ${renderTimeline(timeline)}
            </div>
        </div>
    `;

    container.innerHTML = html;
}

function renderTimeline(timeline) {
    if (!timeline || timeline.length === 0) return '<p class="no-events">No events scheduled.</p>';

    return timeline.map(event => {
        const startTime = new Date(event.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const endTime = new Date(event.end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        let typeClass = 'type-default';
        if (event.type === 'class') typeClass = 'type-class';
        if (event.type === 'task') typeClass = 'type-task';
        if (event.type === 'free') typeClass = 'type-free';

        return `
            <div class="timeline-item ${typeClass}">
                <div class="time">
                    ${startTime}<br>
                    <span>${endTime}</span>
                </div>
                <div class="content">
                    <div class="title">${event.title}</div>
                    <div class="type">${event.type}</div>
                </div>
            </div>
        `;
    }).join('');
}

async function triggerAutoSchedule() {
    showToast('✨ Magic Scheduling...', 'info');
    try {
        const result = await apiCall('/schedule/auto-assign', 'POST');
        if (result.status === 'success') {
            showToast(result.message, 'success');
            renderCalendar(); // Refresh
        } else {
            showToast(result.message, 'info');
        }
    } catch (e) {
        showToast('Failed to auto-schedule', 'error');
    }
}

function previousMonth() {
    currentCalendarDate.setMonth(currentCalendarDate.getMonth() - 1);
    renderCalendar();
}

function nextMonth() {
    currentCalendarDate.setMonth(currentCalendarDate.getMonth() + 1);
    renderCalendar();
}

function showDayDetails(day) {
    // In a full app, this would open a modal with that day's specific details
    console.log(`Clicked day: ${day}`);
}
