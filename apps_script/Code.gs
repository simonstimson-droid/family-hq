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
        result = updateRow(sheet, e.parameter.row, JSON.parse(e.parameter.data));
        break;
      case 'delete':
        result = deleteRow(sheet, e.parameter.row);
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
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  Logger.log('Spreadsheet: ' + ss.getName());
  Logger.log('ID: ' + ss.getId());
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    Logger.log('Sheet ' + i + ': ' + sheets[i].getName());
  }
}
