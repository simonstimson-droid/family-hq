/**
 * Stimson Family HQ - Calendar Sync
 * 
 * Deploy this as a separate Apps Script web app from the email processor.
 * 
 * POST actions:
 *   listEvents — Get events from Google Calendar
 *   createEvent — Create event in Google Calendar  
 *   listSheetEvents — Get events from the Sheet (fallback)
 * 
 * For listEvents:
 *   { action: "listEvents", days: 30 }
 *   Returns: [{ date, time, event, who, location, notes, source }]
 * 
 * For createEvent:
 *   { action: "createEvent", date, time, event, who, location, notes }
 *   Returns: { success: true }
 */

const SPREADSHEET_ID = '1zYs5s66J2nyv-LmaZWBL2Tzhu5vicrkOq3nDC5LSFXA';

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    const action = body.action;
    
    let result;
    switch (action) {
      case 'listEvents':
        result = listCalendarEvents(parseInt(body.days) || 30);
        break;
      case 'createEvent':
        result = createCalendarEvent(body);
        break;
      case 'listSheetEvents':
        result = listSheetEvents();
        break;
      case 'deleteEvent':
        result = deleteCalendarEvent(body.eventId);
        break;
      default:
        result = { error: 'Unknown action: ' + action };
    }
    
    return ContentService.createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
      
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ error: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  const days = parseInt(e.parameter.days) || 30;
  const result = listCalendarEvents(days);
  return ContentService.createTextOutput(JSON.stringify(result))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * List events from Google Calendar + Sheet, deduplicated
 */
function listCalendarEvents(days) {
  const events = [];
  const now = new Date();
  const future = new Date();
  future.setDate(future.getDate() + days);
  
  // 1. Fetch from Google Calendar
  try {
    const calendar = CalendarApp.getCalendarById('family17800354474891822339@group.calendar.google.com');
    if (calendar) {
      const calEvents = calendar.getEvents(now, future);
      calEvents.forEach(e => {
        events.push({
          Date: formatDate(e.getStartTime()),
          Time: e.isAllDayEvent() ? 'All day' : formatTime(e.getStartTime()) + ' - ' + formatTime(e.getEndTime()),
          Event: e.getTitle(),
          Who: e.getDescription() || 'Family',
          Location: e.getLocation() || '',
          Notes: '',
          Source: 'calendar',
          Id: e.getId()
        });
      });
    }
  } catch (err) {
    Logger.log('Calendar fetch error: ' + err.message);
  }
  
  // 2. Fetch from Sheet
  try {
    const sheet = SpreadsheetApp.openById(SPREADSHEET_ID).getSheetByName('📅 Calendar');
    if (sheet) {
      const data = sheet.getDataRange().getValues();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      
      for (let i = 1; i < data.length; i++) {
        const dateStr = data[i][0];
        if (!dateStr) continue;
        
        // Parse date
        let eventDate;
        if (dateStr instanceof Date) {
          eventDate = dateStr;
        } else {
          eventDate = new Date(dateStr.toString() + 'T00:00:00');
        }
        
        if (isNaN(eventDate.getTime())) continue;
        
        // Skip if in past or too far future
        const dayDiff = Math.floor((eventDate - today) / (1000 * 60 * 60 * 24));
        if (dayDiff < -1 || dayDiff > days) continue;
        
        events.push({
          Date: eventDate instanceof Date ? formatDate(eventDate) : dateStr.toString(),
          Time: data[i][1] || '',
          Event: data[i][2] || '',
          Who: data[i][3] || 'Family',
          Location: data[i][4] || '',
          Notes: data[i][5] || '',
          Source: 'sheet'
        });
      }
    }
  } catch (err) {
    Logger.log('Sheet fetch error: ' + err.message);
  }
  
  // Sort by date
  events.sort((a, b) => {
    const da = new Date(a.Date + 'T00:00:00');
    const db = new Date(b.Date + 'T00:00:00');
    return da - db;
  });
  
  return events;
}

/**
 * Create event in Google Calendar
 */
function createCalendarEvent(body) {
  const date = body.date;
  const time = body.time || 'All day';
  const title = body.event || 'Event';
  const who = body.who || 'Family';
  const location = body.location || '';
  const notes = body.notes || '';
  
  const calendar = CalendarApp.getCalendarById('family17800354474891822339@group.calendar.google.com');
  if (!calendar) return { error: 'Calendar not found' };
  
  const startTime = new Date(date + 'T00:00:00');
  
  let event;
  if (time === 'All day') {
    event = calendar.createAllDayEvent(title, startTime, {
      description: who,
      location: location,
      guests: ''
    });
  } else {
    const parts = time.split(':');
    const hours = parseInt(parts[0]) || 0;
    const minutes = parseInt(parts[1]) || 0;
    startTime.setHours(hours, minutes);
    
    const endTime = new Date(startTime);
    endTime.setHours(hours + 1, minutes);
    
    event = calendar.createEvent(title, startTime, endTime, {
      description: who,
      location: location
    });
  }
  
  // Also write to sheet
  try {
    const sheet = SpreadsheetApp.openById(SPREADSHEET_ID).getSheetByName('📅 Calendar');
    if (sheet) {
      sheet.appendRow([date, time, title, who, location, notes]);
    }
  } catch (e) {
    Logger.log('Sheet write error (non-fatal): ' + e.message);
  }
  
  return { success: true };
}

/**
 * Delete event from Google Calendar by ID
 */
function deleteCalendarEvent(eventId) {
  if (!eventId) return { error: 'No eventId provided' };
  try {
    const calendar = CalendarApp.getCalendarById('family17800354474891822339@group.calendar.google.com');
    if (!calendar) return { error: 'Calendar not found' };
    const event = calendar.getEventById(eventId);
    if (event) {
      event.deleteEvent();
      return { success: true };
    }
    return { error: 'Event not found: ' + eventId };
  } catch (err) {
    return { error: err.message };
  }
}

/**
 * List events from Sheet only (fallback)
 */
function listSheetEvents() {
  const events = [];
  try {
    const sheet = SpreadsheetApp.openById(SPREADSHEET_ID).getSheetByName('📅 Calendar');
    if (sheet) {
      const data = sheet.getDataRange().getValues();
      for (let i = 1; i < data.length; i++) {
        if (data[i][2]) {
          events.push({
            Date: data[i][0] || '',
            Time: data[i][1] || '',
            Event: data[i][2] || '',
            Who: data[i][3] || 'Family',
            Location: data[i][4] || '',
            Notes: data[i][5] || '',
            Source: 'sheet'
          });
        }
      }
    }
  } catch (err) {
    Logger.log('Sheet error: ' + err.message);
  }
  return events;
}

// Helpers
function formatDate(d) {
  if (isNaN(d.getTime())) return '';
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatTime(d) {
  if (isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}
