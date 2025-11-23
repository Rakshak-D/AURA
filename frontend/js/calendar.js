// Calendar & Routine Logic
let currentCalendarDate = new Date();
let calendarEvents = [];

async function renderCalendar() {
    const container = document.getElementById('calendar-grid');
    const timelineContainer = document.getElementById('timeline-container');

    if (!container) return;

    const year = currentCalendarDate.getFullYear();
    const month = currentCalendarDate.getMonth();

    // Update Header
    const monthLabel = document.getElementById('current-month');
    if (monthLabel) {
        monthLabel.textContent = currentCalendarDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    }

    // Fetch Routine/Events
    try {
        const routine = await apiCall('/schedule/routine');
        calendarEvents = routine.timeline || [];

        // Render Grid
        renderGrid(container, year, month, calendarEvents);

        // Render Timeline (Today)
        if (timelineContainer) {
            renderTimeline(timelineContainer, calendarEvents);
        }

    } catch (error) {
        console.error('Error fetching calendar:', error);
        showToast('Failed to load calendar', 'error');
    }
}

function renderGrid(container, year, month, events) {
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    let html = '';

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
        const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const isToday = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();

        // Filter events for this day
        const dayEvents = events.filter(e => e.start.startsWith(dateStr));

        let eventsHtml = dayEvents.slice(0, 3).map(e => `
            <div class="event-dot ${e.type === 'class' ? 'event-class' : 'event-task'}" 
                 draggable="true" 
                 ondragstart="handleDragStart(event, '${e.id}', '${e.type}')">
                • ${e.title}
            </div>
        `).join('');

        if (dayEvents.length > 3) {
            eventsHtml += `<div class="event-more">+${dayEvents.length - 3} more</div>`;
        }

        html += `
            <div class="calendar-day${isToday ? ' today' : ''}" 
                 ondragover="handleDragOver(event)" 
                 ondrop="handleDrop(event, '${dateStr}')"
                 onclick="showDayDetails('${dateStr}')">
                <div class="day-number">${day}</div>
                ${eventsHtml}
            </div>
        `;
    }

    container.innerHTML = html;
}

function renderTimeline(container, events) {
    // Filter for today
    const todayStr = new Date().toISOString().split('T')[0];
    const todayEvents = events.filter(e => e.start.startsWith(todayStr));

    if (todayEvents.length === 0) {
        container.innerHTML = '<div class="no-events">No events scheduled for today.</div>';
        return;
    }

    let html = '<h3>Today\'s Timeline</h3><div class="timeline-list">';

    html += todayEvents.map(e => `
        <div class="timeline-item type-${e.type}">
            <div class="time">
                <span>${formatTime(e.start)}</span>
                <span class="duration">${getDuration(e.start, e.end)}m</span>
            </div>
            <div class="content">
                <div class="title">${e.title}</div>
                <div class="type">${e.type}</div>
            </div>
        </div>
    `).join('');

    html += '</div>';
    container.innerHTML = html;
}

// Drag & Drop Handlers
function handleDragStart(e, id, type) {
    e.dataTransfer.setData('text/plain', JSON.stringify({ id, type }));
    e.dataTransfer.effectAllowed = 'move';
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    e.currentTarget.classList.add('drag-over');
}

async function handleDrop(e, dateStr) {
    e.preventDefault();
    e.currentTarget.classList.remove('drag-over');

    const data = JSON.parse(e.dataTransfer.getData('text/plain'));

    if (data.type !== 'task') {
        showToast('Only tasks can be rescheduled', 'warning');
        return;
    }

    // Call API to update task due date
    // We need to keep the time, just change the date.
    // Or set to default time on that date.
    // For simplicity, let's set to 9 AM on that date.
    const newDate = `${dateStr}T09:00:00`;

    try {
        await apiCall(`/tasks/${data.id}`, 'PUT', { due_date: newDate });
        showToast('Task rescheduled', 'success');
        renderCalendar(); // Refresh
    } catch (error) {
        showToast('Failed to reschedule task', 'error');
    }
}

// Helpers
function formatTime(isoString) {
    return new Date(isoString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function getDuration(start, end) {
    const s = new Date(start);
    const e = new Date(end);
    return Math.round((e - s) / 60000);
}

function previousMonth() {
    currentCalendarDate.setMonth(currentCalendarDate.getMonth() - 1);
    renderCalendar();
}

function nextMonth() {
    currentCalendarDate.setMonth(currentCalendarDate.getMonth() + 1);
    renderCalendar();
}

async function triggerAutoSchedule() {
    showToast('Magic Schedule running...', 'info');
    try {
        const result = await apiCall('/schedule/auto-assign', 'POST');
        showToast(result.message, 'success');
        renderCalendar();
    } catch (error) {
        showToast('Auto-schedule failed', 'error');
    }
}

function showDayDetails(dateStr) {
    if (window.openTaskModal) {
        window.openTaskModal(dateStr);
    } else {
        console.error('openTaskModal not found');
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('calendar-view').classList.contains('active')) {
        renderCalendar();
    }
});

// Observer
const calendarObserver = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
        if (mutation.target.id === 'calendar-view' && mutation.target.classList.contains('active')) {
            renderCalendar();
        }
    });
});

const calendarView = document.getElementById('calendar-view');
if (calendarView) {
    calendarObserver.observe(calendarView, { attributes: true });
}
