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
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  Logger.log('Spreadsheet: ' + ss.getName());
  Logger.log('ID: ' + ss.getId());
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    Logger.log('Sheet ' + i + ': ' + sheets[i].getName());
  }
}
