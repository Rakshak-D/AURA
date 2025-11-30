// Calendar Logic: Professional Daily Timeline View
let currentCalendarDate = new Date();
let calendarEvents = [];
const PIXELS_PER_MINUTE = 2; // 2px per minute = 120px per hour
const TIMELINE_START_HOUR = 0; // Start from midnight
const TIMELINE_END_HOUR = 24; // End at midnight next day

// Ensure API_URL is available (fallback if main.js hasn't loaded)
const CALENDAR_API_URL = typeof API_URL !== 'undefined' ? API_URL : '/api';

// Update date header immediately when script loads (if element exists)
(function () {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(() => {
                const header = document.getElementById('calendar-date-header');
                if (header && header.textContent === 'Loading...') {
                    updateDateHeader();
                }
            }, 10);
        });
    } else {
        setTimeout(() => {
            const header = document.getElementById('calendar-date-header');
            if (header && header.textContent === 'Loading...') {
                updateDateHeader();
            }
        }, 10);
    }
})();

// Initialize calendar when view becomes active
document.addEventListener('DOMContentLoaded', () => {
    console.log('Calendar.js: DOMContentLoaded fired');

    // Update date header immediately on page load (even if view not active)
    setTimeout(() => {
        updateDateHeader();
    }, 50);

    // Check if calendar view exists
    const calendarView = document.getElementById('view-calendar');
    if (calendarView) {
        console.log('Calendar view element found');

        // Observer for view switching
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.target.classList.contains('active')) {
                    console.log('Calendar view activated via MutationObserver');
                    setTimeout(() => {
                        updateDateHeader();
                        renderCalendar();
                    }, 100);
                }
            });
        });
        observer.observe(calendarView, { attributes: true, attributeFilter: ['class'] });

        // Initial render if already active
        if (calendarView.classList.contains('active')) {
            console.log('Calendar view already active on load');
            setTimeout(() => {
                updateDateHeader();
                renderCalendar();
            }, 200);
        }

        // Fallback: Check every second if view becomes active (for 10 seconds)
        let checkCount = 0;
        const fallbackCheck = setInterval(() => {
            checkCount++;
            if (calendarView.classList.contains('active')) {
                console.log('Calendar view detected as active via fallback check');
                updateDateHeader();
                renderCalendar();
                clearInterval(fallbackCheck);
            } else if (checkCount >= 10) {
                clearInterval(fallbackCheck);
            }
        }, 1000);
    } else {
        console.error('Calendar view element not found - #view-calendar does not exist');
    }
});

async function renderCalendar() {
    console.log('renderCalendar() called');

    const container = document.getElementById('calendar-timeline');
    if (!container) {
        console.error('Calendar timeline container not found - element #calendar-timeline does not exist');
        return;
    }

    console.log('Container found, updating date header...');
    // Update date header immediately
    updateDateHeader();

    // Show loading state
    container.innerHTML = '<div class="loading-state" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; color: var(--text-muted);"><div style="margin-bottom: 1rem;">Loading calendar...</div></div>';

    // Format date for API
    const dateStr = formatDateForAPI(currentCalendarDate);
    const apiUrl = typeof API_URL !== 'undefined' ? API_URL : '/api';

    console.log('Making API request to:', `${apiUrl}/schedule/routine?date=${dateStr}`);

    try {
        const response = await fetch(`${apiUrl}/schedule/routine?date=${dateStr}`);

        console.log('API Response status:', response.status);

        if (!response.ok) {
            const errorText = await response.text();
            console.error('API Error Response:', response.status, errorText);
            throw new Error(`Failed to fetch schedule: ${response.status} - ${errorText.substring(0, 100)}`);
        }

        const routine = await response.json();
        console.log('Calendar data received:', routine);
        calendarEvents = routine.timeline || [];
        console.log('Number of events:', calendarEvents.length);

        renderTimelineView(container, calendarEvents);
    } catch (error) {
        console.error('Error fetching calendar:', error);
        const errorMsg = error.message || 'Failed to load schedule';
        container.innerHTML = `
            <div class="error-state" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; color: var(--text-muted); padding: 2rem;">
                <i data-lucide="alert-circle" style="width: 48px; height: 48px; margin-bottom: 1rem; opacity: 0.5;"></i>
                <p style="margin-bottom: 0.5rem;">${errorMsg}</p>
                <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">Check browser console (F12) for details</p>
                <button onclick="window.renderCalendar()" style="margin-top: 1rem; padding: 0.5rem 1rem; background: var(--primary-color); color: white; border: none; border-radius: 4px; cursor: pointer;">Retry</button>
            </div>`;

        // Re-initialize icons for error state
        if (typeof lucide !== 'undefined') {
            setTimeout(() => lucide.createIcons(), 100);
        }
    }
}

function updateDateHeader() {
    const headerElement = document.getElementById('calendar-date-header');
    if (headerElement) {
        try {
            const options = { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' };
            const dateString = currentCalendarDate.toLocaleDateString('en-US', options);
            headerElement.textContent = dateString;
            console.log('Date header updated to:', dateString);
        } catch (error) {
            console.error('Error updating date header:', error);
            headerElement.textContent = currentCalendarDate.toISOString().split('T')[0];
        }
    } else {
        console.warn('Calendar date header element not found');
    }
}

function formatDateForAPI(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function renderTimelineView(container, events) {
    // Clear container
    container.innerHTML = '';

    // Generate time labels
    generateTimeLabels();

    // Create hour grid lines - exactly matching time label positions
    for (let hour = TIMELINE_START_HOUR; hour < TIMELINE_END_HOUR; hour++) {
        const gridLine = document.createElement('div');
        gridLine.className = 'timeline-hour-line';
        // Each hour line is at hour * 60 minutes * PIXELS_PER_MINUTE
        gridLine.style.top = `${hour * 60 * PIXELS_PER_MINUTE}px`;
        container.appendChild(gridLine);
    }

    // Render events
    if (events && events.length > 0) {
        events.forEach(event => {
            if (event.type === 'free') return; // Skip free blocks in visual rendering

            try {
                const eventElement = createEventElement(event);
                container.appendChild(eventElement);
            } catch (error) {
                console.error('Error rendering event:', event, error);
            }
        });
    } else {
        // Show empty state
        const emptyState = document.createElement('div');
        emptyState.className = 'empty-state';
        emptyState.style.cssText = 'position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; color: var(--text-muted); padding: 2rem;';
        emptyState.innerHTML = `
            <i data-lucide="calendar-x" style="width: 48px; height: 48px; margin-bottom: 1rem; opacity: 0.5;"></i>
            <p>No events scheduled for this day</p>
            <p style="font-size: 0.85rem; margin-top: 0.5rem;">Click anywhere on the timeline to add an event</p>
        `;
        container.appendChild(emptyState);
    }

    // Remove existing click listener and add new one
    container.removeEventListener('click', handleTimelineClick);
    container.addEventListener('click', handleTimelineClick);

    // Re-initialize icons
    if (typeof lucide !== 'undefined') {
        setTimeout(() => lucide.createIcons(), 100);
    }
}

function createEventElement(event) {
    // Parse ISO strings - JavaScript Date automatically converts UTC to local time
    const start = new Date(event.start_time || event.start);
    const end = new Date(event.end_time || event.end);

    // Validate dates
    if (isNaN(start.getTime()) || isNaN(end.getTime())) {
        console.error('Invalid date in event:', event);
        return null;
    }

    // Calculate position using strict pixel-per-minute math
    // Get hours and minutes from the local time (already converted from UTC)
    const startMinutes = start.getHours() * 60 + start.getMinutes();
    
    // Calculate duration in minutes
    const durationMinutes = Math.round((end - start) / (1000 * 60));
    
    // Calculate pixel positions
    const top = startMinutes * PIXELS_PER_MINUTE;
    const height = Math.max(durationMinutes * PIXELS_PER_MINUTE, 30); // Minimum 30px height

    // Create event element
    const eventDiv = document.createElement('div');
    eventDiv.className = `calendar-event event-${event.type}`;
    eventDiv.style.top = `${top}px`;
    eventDiv.style.height = `${height}px`;
    eventDiv.dataset.eventId = event.id || '';
    eventDiv.dataset.eventType = event.type;

    // Set color from event or use default
    const color = event.color || getDefaultColor(event.type, event.priority);
    eventDiv.style.borderLeftColor = color;
    eventDiv.style.background = `${color}15`; // 15% opacity

    // Event content
    const title = document.createElement('div');
    title.className = 'event-title';
    title.textContent = event.title || 'Untitled Event';

    const time = document.createElement('div');
    time.className = 'event-time';
    time.textContent = formatTimeRange(start, end);

    eventDiv.appendChild(title);
    eventDiv.appendChild(time);

    // Add description if available
    if (event.description) {
        const desc = document.createElement('div');
        desc.className = 'event-description';
        desc.textContent = event.description.length > 50
            ? event.description.substring(0, 47) + '...'
            : event.description;
        eventDiv.appendChild(desc);
    }

    // Click handler
    eventDiv.addEventListener('click', (e) => {
        e.stopPropagation();
        openEventModal(event);
    });

    return eventDiv;
}

function getDefaultColor(type, priority) {
    const colorMap = {
        'task': {
            'urgent': '#EF4444',
            'high': '#F59E0B',
            'medium': '#3B82F6',
            'low': '#6B7280'
        },
        'routine': '#10B981',
        'class': '#10B981',
        'work': '#3B82F6',
        'meal': '#F59E0B',
        'break': '#6B7280',
        'prep': '#6366F1',
        'event': '#8B5CF6'
    };

    if (type === 'task' && priority) {
        return colorMap.task[priority] || colorMap.task.medium;
    }

    return colorMap[type] || '#3B82F6';
}

function formatTimeRange(start, end) {
    const formatTime = (date) => {
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: true
        });
    };
    return `${formatTime(start)} - ${formatTime(end)}`;
}

function handleTimelineClick(e) {
    // Only handle clicks on the timeline background, not on events
    if (e.target.classList.contains('calendar-event') ||
        e.target.closest('.calendar-event') ||
        e.target.classList.contains('timeline-hour-line')) {
        return;
    }

    // Calculate clicked time relative to the day-view container
    const dayView = e.currentTarget;
    const rect = dayView.getBoundingClientRect();
    const clickY = e.clientY - rect.top;
    const clickedMinutes = Math.floor(clickY / PIXELS_PER_MINUTE);
    const clickedHour = Math.floor(clickedMinutes / 60);
    const clickedMinute = clickedMinutes % 60;

    // Create datetime for clicked time (in local timezone)
    const clickedDate = new Date(currentCalendarDate);
    clickedDate.setHours(clickedHour, clickedMinute, 0, 0);

    // Open modal to create event at this time
    openEventModal(null, clickedDate);
}

function openEventModal(event = null, startTime = null) {
    // If event exists, we're editing; otherwise creating new
    if (event && event.type === 'task' && event.id) {
        // Open task edit modal
        if (typeof openEditModal === 'function') {
            openEditModal(event.id);
        }
    } else {
        // Open new event/task modal
        if (startTime) {
            // Pre-fill time in task modal based on clicked position
            if (typeof openTaskModal === 'function') {
                openTaskModal();
                // Set the date/time in the modal
                // Convert to local datetime string format (YYYY-MM-DDTHH:mm)
                setTimeout(() => {
                    const dateInput = document.getElementById('task-date');
                    if (dateInput) {
                        // Format as local datetime for datetime-local input
                        const year = startTime.getFullYear();
                        const month = String(startTime.getMonth() + 1).padStart(2, '0');
                        const day = String(startTime.getDate()).padStart(2, '0');
                        const hours = String(startTime.getHours()).padStart(2, '0');
                        const minutes = String(startTime.getMinutes()).padStart(2, '0');
                        const localDateTimeString = `${year}-${month}-${day}T${hours}:${minutes}`;
                        dateInput.value = localDateTimeString;
                    }
                }, 100);
            }
        } else if (typeof openTaskModal === 'function') {
            openTaskModal();
        }
    }
}

// Navigation functions
function prevDay() {
    currentCalendarDate.setDate(currentCalendarDate.getDate() - 1);
    renderCalendar();
}

function nextDay() {
    currentCalendarDate.setDate(currentCalendarDate.getDate() + 1);
    renderCalendar();
}

function goToToday() {
    currentCalendarDate = new Date();
    renderCalendar();
}

// Magic Schedule function
async function autoSchedule() {
    const dateStr = formatDateForAPI(currentCalendarDate);
    const apiUrl = typeof API_URL !== 'undefined' ? API_URL : '/api';

    if (typeof showToast === 'function') {
        showToast('Magic Schedule running...', 'info');
    }

    try {
        const response = await fetch(`${apiUrl}/schedule/auto-assign?date=${dateStr}`, {
            method: 'POST'
        });

        if (!response.ok) throw new Error('Auto-schedule failed');

        const result = await response.json();

        // Animate new tasks
        if (typeof showToast === 'function') {
            showToast(result.message || `Scheduled ${result.scheduled || 0} tasks`, 'success');
        }

        // Refresh calendar with animation
        setTimeout(() => {
            renderCalendar();
        }, 500);

    } catch (error) {
        console.error('Auto-schedule error:', error);
        if (typeof showToast === 'function') {
            showToast('Auto-schedule failed. Please try again.', 'error');
        }
    }
}

// Generate time labels
function generateTimeLabels() {
    const labelsContainer = document.querySelector('.time-labels-container');
    if (!labelsContainer) {
        console.warn('Time labels container not found');
        return;
    }

    labelsContainer.innerHTML = '';

    // Generate labels for each hour, matching grid line positions exactly
    for (let hour = TIMELINE_START_HOUR; hour < TIMELINE_END_HOUR; hour++) {
        const label = document.createElement('div');
        label.className = 'time-label';
        label.textContent = `${String(hour).padStart(2, '0')}:00`;
        // Position matches grid lines: hour * 60 minutes * PIXELS_PER_MINUTE
        label.style.top = `${hour * 60 * PIXELS_PER_MINUTE}px`;
        labelsContainer.appendChild(label);
    }
}

// Export for global access - make sure these are available immediately
window.prevDay = function () {
    currentCalendarDate.setDate(currentCalendarDate.getDate() - 1);
    updateDateHeader();
    renderCalendar();
};

window.nextDay = function () {
    currentCalendarDate.setDate(currentCalendarDate.getDate() + 1);
    updateDateHeader();
    renderCalendar();
};

window.goToToday = function () {
    currentCalendarDate = new Date();
    updateDateHeader();
    renderCalendar();
};

window.autoSchedule = autoSchedule;
window.renderCalendar = renderCalendar;
window.updateDateHeader = updateDateHeader;

// Force initialization check
setTimeout(() => {
    const calendarView = document.getElementById('view-calendar');
    if (calendarView && calendarView.classList.contains('active')) {
        console.log('Calendar view is active, forcing render...');
        updateDateHeader();
        renderCalendar();
    }
}, 500);

// Debug function - call from browser console: testCalendar()
window.testCalendar = function () {
    console.log('=== CALENDAR DEBUG TEST ===');
    console.log('1. Checking elements...');
    const header = document.getElementById('calendar-date-header');
    const container = document.getElementById('calendar-timeline');
    const view = document.getElementById('view-calendar');

    console.log('Date header element:', header ? 'FOUND' : 'NOT FOUND', header);
    console.log('Timeline container:', container ? 'FOUND' : 'NOT FOUND', container);
    console.log('Calendar view:', view ? 'FOUND' : 'NOT FOUND', view);
    console.log('View is active:', view?.classList.contains('active'));

    console.log('2. Testing date header update...');
    updateDateHeader();

    console.log('3. Testing API call...');
    const dateStr = formatDateForAPI(currentCalendarDate);
    const apiUrl = typeof API_URL !== 'undefined' ? API_URL : '/api';
    console.log('API URL:', `${apiUrl}/schedule/routine?date=${dateStr}`);

    fetch(`${apiUrl}/schedule/routine?date=${dateStr}`)
        .then(r => {
            console.log('Response status:', r.status);
            return r.json();
        })
        .then(data => {
            console.log('API Response:', data);
            console.log('Timeline events:', data.timeline?.length || 0);
        })
        .catch(err => {
            console.error('API Error:', err);
        });

    console.log('4. Attempting to render...');
    renderCalendar();
    console.log('=== TEST COMPLETE ===');
};
