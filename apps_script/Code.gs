// Google Apps Script for Family HQ
// Deploy as a web app to enable the dashboard to read AND write to this spreadsheet

// Configuration
// NOTE: This is a STANDALONE Apps Script (not bound to the spreadsheet), so
// SpreadsheetApp.getActiveSpreadsheet() returns null here. Calling .getId()
// on it throws "Cannot read properties of null (reading 'getId')" on EVERY
// script load — which is exactly the error that fired ~every 5 min from the
// orphaned processEmails time trigger (function no longer exists in code).
// Use the sheet ID directly. Hardcoding is safe and avoids the runtime crash.
var SPREADSHEET_ID = '1zYs5s66J2nyv-LmaZWBL2Tzhu5vicrkOq3nDC5LSFXA';

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
          // Find and update by search
          result = findAndUpdateRow(sheet, e.parameter.searchCol, e.parameter.searchVal, e.parameter.updateCol, e.parameter.updateVal);
        } else {
          result = updateRow(sheet, e.parameter.row, JSON.parse(e.parameter.data));
        }
        break;
      case 'delete':
        if (e.parameter.searchCol && e.parameter.searchVal) {
          // Find and delete by search
          result = findAndDeleteRow(sheet, e.parameter.searchCol, e.parameter.searchVal);
        } else {
          result = deleteRow(sheet, e.parameter.row);
        }
        break;
      case 'toggleDone':
        var toggleResult = findAndUpdateRow(sheet, 'Item', e.parameter.item, 'Done ✓', e.parameter.done ? '✓' : '');
        result = toggleResult;
        break;
      default:
        result = {error: 'Unknown action: ' + action};
    }
  } catch(err) {
    result = {error: err.toString()};
  }

  var output = JSON.stringify(result);
  return ContentService.createTextOutput(output)
    .setMimeType(ContentService.MimeType.JSON);
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

// ===== HELPER =====

function getSheetByEmoji(ss, emojiPrefix) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getName().startsWith(emojiPrefix)) {
      return sheets[i];
    }
  }
  return null;
}

// ===== SETUP FUNCTION =====
// Run this once after pasting the script to verify it works
function testSetup() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  Logger.log('Spreadsheet: ' + ss.getName());
  Logger.log('ID: ' + ss.getId());
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    Logger.log('Sheet ' + i + ': ' + sheets[i].getName());
  }
}

// ===== TRIGGER MAINTENANCE (run via `clasp run`) =====
// List all project triggers with their handler function names.
function listTriggers2() {
  return ScriptApp.getProjectTriggers().map(function(t) {
    return {
      id: t.getUniqueId(),
      handler: t.getHandlerFunction(),
      type: (t.getEventType ? t.getEventType() : 'unknown').toString()
    };
  });
}

// Delete the orphaned processEmails time trigger (function no longer exists
// in code, so it throws on every fire). Safe: only targets known-dead
// handler names; leaves any real triggers untouched.
function removeOrphanTriggers() {
  var targets = ['processEmails', 'processEmail'];
  var all = ScriptApp.getProjectTriggers();
  var deleted = [];
  all.forEach(function(t) {
    if (targets.indexOf(t.getHandlerFunction()) !== -1) {
      ScriptApp.deleteTrigger(t);
      deleted.push(t.getUniqueId());
    }
  });
  // Re-list to report what remains.
  var remaining = ScriptApp.getProjectTriggers().map(function(t) {
    return t.getHandlerFunction();
  });
  return {deleted: deleted, remaining: remaining};
}
