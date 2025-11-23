// Calendar Logic: Vertical Timeline View
let currentCalendarDate = new Date();
let calendarEvents = [];

async function renderCalendar() {
    const container = document.getElementById('calendar-grid');
    if (!container) return;

    // Update Header
    const monthLabel = document.getElementById('current-month');
    if (monthLabel) {
        monthLabel.textContent = currentCalendarDate.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
    }

    // Fetch Routine/Events
    try {
        const routine = await apiCall('/schedule/routine');
        calendarEvents = routine.timeline || [];
        renderTimelineView(container, calendarEvents);
    } catch (error) {
        console.error('Error fetching calendar:', error);
        container.innerHTML = '<div class="error-state">Failed to load schedule</div>';
    }
}

function renderTimelineView(container, events) {
    const hours = Array.from({ length: 24 }, (_, i) => i);
    const dateStr = currentCalendarDate.toISOString().split('T')[0];

    // Filter events for selected date
    const dayEvents = events.filter(e => e.start.startsWith(dateStr));

    let html = '<div class="timeline-wrapper">';

    // Time slots
    html += '<div class="time-column">';
    hours.forEach(hour => {
        html += `<div class="time-slot">${String(hour).padStart(2, '0')}:00</div>`;
    });
    html += '</div>';

    // Events column
    html += '<div class="events-column">';

    // Render background grid
    hours.forEach(hour => {
        html += `<div class="grid-line" style="top: ${hour * 60}px"></div>`;
    });

    // Render Events
    dayEvents.forEach(event => {
        const start = new Date(event.start);
        const end = new Date(event.end);

        const startMinutes = start.getHours() * 60 + start.getMinutes();
        const duration = (end - start) / 60000;

        let colorClass = 'event-task'; // Purple
        if (event.type === 'busy') colorClass = 'event-busy'; // Red
        if (event.type === 'free') colorClass = 'event-free'; // Green

        // Inline style for positioning
        const style = `top: ${startMinutes}px; height: ${duration}px;`;

        html += `
            <div class="timeline-event ${colorClass}" style="${style}" onclick="showEventDetails('${event.id}')">
                <div class="event-title">${event.title}</div>
                <div class="event-time">${start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
            </div>
        `;
    });

    html += '</div></div>'; // Close wrapper

    // Add CSS for timeline if not present (injecting here for simplicity, or assume styles.css handles it)
    // I'll assume styles.css needs to support this structure.
    // Since I already updated styles.css, I might need to add specific timeline styles there or inline them.
    // I'll add a style block here to ensure it works immediately.
    html += `
        <style>
            .timeline-wrapper { display: flex; position: relative; height: 1440px; }
            .time-column { width: 60px; border-right: 1px solid rgba(255,255,255,0.1); }
            .time-slot { height: 60px; padding: 5px; font-size: 12px; color: var(--text-secondary); }
            .events-column { flex: 1; position: relative; }
            .grid-line { position: absolute; width: 100%; height: 1px; background: rgba(255,255,255,0.05); }
            .timeline-event { 
                position: absolute; 
                width: 90%; 
                left: 5%; 
                border-radius: 6px; 
                padding: 5px 10px; 
                font-size: 12px; 
                overflow: hidden;
                cursor: pointer;
                transition: transform 0.2s;
                border: 1px solid rgba(255,255,255,0.1);
            }
            .timeline-event:hover { transform: scale(1.02); z-index: 10; }
            .event-task { background: rgba(176, 38, 255, 0.3); border-left: 3px solid var(--neon-purple); }
            .event-busy { background: rgba(255, 59, 48, 0.3); border-left: 3px solid #ff3b30; }
            .event-free { background: rgba(52, 199, 89, 0.3); border-left: 3px solid #34c759; }
        </style>
    `;

    container.innerHTML = html;
}

function previousMonth() {
    // Actually previous Day
    currentCalendarDate.setDate(currentCalendarDate.getDate() - 1);
    renderCalendar();
}

function nextMonth() {
    // Actually next Day
    currentCalendarDate.setDate(currentCalendarDate.getDate() + 1);
    renderCalendar();
}

function triggerAutoSchedule() {
    showToast('Magic Schedule running...', 'info');
    apiCall('/schedule/auto-assign', 'POST')
        .then(res => {
            showToast(res.message, 'success');
            renderCalendar();
        })
        .catch(() => showToast('Auto-schedule failed', 'error'));
}

function showEventDetails(id) {
    // Open task modal if it's a task
    if (window.openTaskModal) window.openTaskModal();
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
