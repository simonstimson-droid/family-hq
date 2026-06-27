// Google Apps Script for Family HQ
// Deploy as a web app to enable the dashboard to read AND write to this spreadsheet

// Configuration
var SPREADSHEET_ID = SpreadsheetApp.getActiveSpreadsheet().getId();

// ===== WEB APP ENTRY POINTS =====

function doGet(e) {
  return handleRequest(e);
}

function doPost(e) {
  return handleRequest(e);
}

function handleRequest(e) {
  var action = e.parameter.action;
  var sheet = e.parameter.sheet;
  var result;
  
  try {
    switch(action) {
      case 'append':
        result = appendRow(sheet, JSON.parse(e.parameter.data));
        break;
      case 'update':
        if (e.parameter.searchCol && e.parameter.searchVal) {
          result = findAndUpdateRow(sheet, e.parameter.searchCol, e.parameter.searchVal, e.parameter.updateCol, e.parameter.updateVal);
        } else {
          result = updateRow(sheet, e.parameter.row, JSON.parse(e.parameter.data));
        }
        break;
      case 'delete':
        if (e.parameter.searchCol && e.parameter.searchVal) {
          result = findAndDeleteRow(sheet, e.parameter.searchCol, e.parameter.searchVal);
        } else {
          result = deleteRow(sheet, e.parameter.row);
        }
        break;
      case 'toggleDone':
        var toggleResult = findAndUpdateRow(sheet, 'Item', e.parameter.item, 'Done ✓', e.parameter.done ? '✓' : '');
        result = toggleResult;
        break;
      case 'listEvents':
        result = listCalendarEvents(parseInt(e.parameter.days) || 30);
        break;
      default:
        result = listCalendarEvents(30); // Default: return calendar events
    }
  } catch(err) {
    result = {error: err.toString()};
  }
  
  var output = JSON.stringify(result);
  return ContentService.createTextOutput(output)
    .setMimeType(ContentService.MimeType.JSON);
}

function listCalendarEvents(days) {
  var events = [];
  var now = new Date();
  var future = new Date();
  future.setDate(future.getDate() + days);
  try {
    var calendar = CalendarApp.getCalendarById('family17800354474891822339@group.calendar.google.com');
    var calEvents = calendar.getEvents(now, future);
    calEvents.forEach(function(e) {
      events.push({
        Date: formatDate(e.getStartTime()),
        Time: e.isAllDayEvent() ? 'All day' : formatTime(e.getStartTime()) + ' - ' + formatTime(e.getEndTime()),
        Event: e.getTitle(),
        Who: e.getDescription() || 'Family',
        Location: e.getLocation() || '',
        Notes: '',
        Source: 'calendar'
      });
    });
  } catch(err) {}
  events.sort(function(a,b){return new Date(a.Date) - new Date(b.Date)});
  return events;
}

// ===== SHEET OPERATIONS =====

function appendRow(sheetName, data) {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = getSheetByEmoji(ss, sheetName);
  if (!sheet) return {error: 'Sheet not found: ' + sheetName};
  
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var row = [];
  for (var i = 0; i < headers.length; i++) {
    var h = headers[i];
    row.push(data[h] !== undefined ? data[h] : '');
  }
  
  sheet.appendRow(row);
  return {success: true, row: sheet.getLastRow(), message: 'Added to ' + sheetName};
}

function updateRow(sheetName, rowNum, data) {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = getSheetByEmoji(ss, sheetName);
  if (!sheet) return {error: 'Sheet not found: ' + sheetName};
  
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  for (var i = 0; i < headers.length; i++) {
    var h = headers[i];
    if (data[h] !== undefined) {
      sheet.getRange(parseInt(rowNum), i + 1).setValue(data[h]);
    }
  }
  return {success: true, message: 'Updated row ' + rowNum + ' in ' + sheetName};
}

function deleteRow(sheetName, rowNum) {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = getSheetByEmoji(ss, sheetName);
  if (!sheet) return {error: 'Sheet not found: ' + sheetName};
  
  sheet.deleteRow(parseInt(rowNum));
  return {success: true, message: 'Deleted row ' + rowNum + ' from ' + sheetName};
}

function findAndUpdateRow(sheetName, searchCol, searchVal, updateCol, updateVal) {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = getSheetByEmoji(ss, sheetName);
  if (!sheet) return {error: 'Sheet not found: ' + sheetName};
  
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var colIdx = -1;
  for (var i = 0; i < headers.length; i++) {
    if (headers[i] === searchCol) { colIdx = i + 1; break; }
  }
  if (colIdx === -1) return {error: 'Column not found: ' + searchCol};
  
  var updateColIdx = -1;
  for (var i = 0; i < headers.length; i++) {
    if (headers[i] === updateCol) { updateColIdx = i + 1; break; }
  }
  if (updateColIdx === -1) return {error: 'Update column not found: ' + updateCol};
  
  var data = sheet.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (data[i][colIdx - 1] && data[i][colIdx - 1].toString().toLowerCase().trim() === searchVal.toLowerCase().trim()) {
      sheet.getRange(i + 1, updateColIdx).setValue(updateVal);
      return {success: true, message: 'Updated "' + searchVal + '" in ' + sheetName};
    }
  }
  return {error: 'Item not found: ' + searchVal};
}

function findAndDeleteRow(sheetName, searchCol, searchVal) {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = getSheetByEmoji(ss, sheetName);
  if (!sheet) return {error: 'Sheet not found: ' + sheetName};
  
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var colIdx = -1;
  for (var i = 0; i < headers.length; i++) {
    if (headers[i] === searchCol) { colIdx = i + 1; break; }
  }
  if (colIdx === -1) return {error: 'Column not found: ' + searchCol};
  
  var data = sheet.getDataRange().getValues();
  for (var i = data.length - 1; i >= 1; i--) {
    if (data[i][colIdx - 1] && data[i][colIdx - 1].toString().toLowerCase().trim() === searchVal.toLowerCase().trim()) {
      sheet.deleteRow(i + 1);
      return {success: true, message: 'Deleted "' + searchVal + '" from ' + sheetName};
    }
  }
  return {error: 'Item not found: ' + searchVal};
}

function getSheetByEmoji(ss, emojiPrefix) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getName().startsWith(emojiPrefix)) {
      return sheets[i];
    }
  }
  return null;
}

function formatDate(d) {
  if (isNaN(d.getTime())) return '';
  var year = d.getFullYear();
  var month = String(d.getMonth() + 1).padStart(2, '0');
  var day = String(d.getDate()).padStart(2, '0');
  return year + '-' + month + '-' + day;
}

function formatTime(d) {
  if (isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}
