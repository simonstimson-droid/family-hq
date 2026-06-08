/**
 * Stimson Family HQ - Email-to-Sheet Processor
 * 
 * SETUP INSTRUCTIONS:
 * 1. Create a new Gmail account (e.g. stimson.family.hq@gmail.com)
 * 2. Go to script.google.com and create a new project
 * 3. Paste this code into the script editor
 * 4. Set up a trigger: Edit -> Current project's triggers -> Add trigger
 *    - Function: processEmails
 *    - Event source: Time-driven
 *    - Type: Minutes timer -> Every 5 minutes
 * 5. Authorize the script when prompted
 * 
 * EMAIL FORMAT (put in subject line):
 *   SHOPPING: Item name | Quantity | Category
 *   CHORES: Task | Assigned To | Frequency
 *   EVENT: Event name | Date (DD/MM/YYYY) | Time | Who | Location
 *   NEWS: Message | Priority (Info/High)
 *   CONTACT: Name | Phone | Email | Type | Notes
 *   MEAL: Day | What
 * 
 * Examples:
 *   SHOPPING: Milk | 2 pints | Dairy
 *   CHORES: Empty bins | Simon | Weekly
 *   EVENT: Ava dentist | 15/06/2026 | 14:00 | Ava | Hitchin Surgery
 *   NEWS: School trip payment due Friday | High
 *   CONTACT: Dr Smith | 01462 123456 | dr@smith.co.uk | Doctor | New GP
 *   MEAL: Monday | Spaghetti Bolognese
 */

// === CONFIGURATION ===
// Replace with your Family HQ Spreadsheet ID
const SPREADSHEET_ID = '1zYs5s66J2nyv-LmaZWBL2Tzhu5vicrkOq3nDC5LSFXA';

// Label to mark processed emails (creates automatically)
const PROCESSED_LABEL = 'FamilyHQ_Processed';

// Error label
const ERROR_LABEL = 'FamilyHQ_Error';

/**
 * Main function - run this on a timer to process emails
 */
function processEmails() {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  
  // Get or create labels
  let processedLabel = GmailApp.getUserLabelByName(PROCESSED_LABEL);
  if (!processedLabel) processedLabel = GmailApp.createLabel(PROCESSED_LABEL);
  
  let errorLabel = GmailApp.getUserLabelByName(ERROR_LABEL);
  if (!errorLabel) errorLabel = GmailApp.createLabel(ERROR_LABEL);
  
  // Search for unread emails in inbox (not already processed)
  const threads = GmailApp.search('in:inbox -label:' + PROCESSED_LABEL + ' -label:' + ERROR_LABEL, 0, 20);
  
  Logger.log('Found ' + threads.length + ' threads to process');
  
  for (const thread of threads) {
    const messages = thread.getMessages();
    for (const message of messages) {
      try {
        const subject = message.getSubject().trim();
        const body = message.getPlainBody().trim();
        const from = message.getFrom();
        
        Logger.log('Processing: ' + subject);
        
        // Parse the subject line for the action type
        const separator = subject.indexOf(':');
        if (separator === -1) {
          // No recognized format - mark as processed so we don't retry
          thread.addLabel(processedLabel);
          continue;
        }
        
        const action = subject.substring(0, separator).trim().toUpperCase();
        const content = subject.substring(separator + 1).trim();
        
        let success = false;
        
        switch (action) {
          case 'SHOPPING':
            success = processShopping(ss, content, from);
            break;
          case 'CHORES':
          case 'CHORE':
            success = processChores(ss, content, from);
            break;
          case 'EVENT':
            success = processEvent(ss, content, from);
            break;
          case 'NEWS':
          case 'ANNOUNCEMENT':
            success = processNews(ss, content, from);
            break;
          case 'CONTACT':
            success = processContact(ss, content, from);
            break;
          case 'MEAL':
          case 'DINNER':
            success = processMeal(ss, content, from);
            break;
          default:
            Logger.log('Unknown action: ' + action);
        }
        
        if (success) {
          thread.addLabel(processedLabel);
          Logger.log('✅ Processed: ' + action + ' - ' + content);
        } else {
          thread.addLabel(errorLabel);
          Logger.log('❌ Format error: ' + subject);
        }
        
      } catch (e) {
        Logger.log('Error processing message: ' + e.message);
        thread.addLabel(errorLabel);
      }
    }
  }
}

function processShopping(ss, content, from) {
  const parts = content.split('|').map(p => p.trim());
  const item = parts[0] || content;
  const quantity = parts[1] || '';
  const category = parts[2] || '';
  const addedBy = extractName(from);
  
  const sheet = ss.getSheetByName('🛒 Shopping List');
  if (!sheet) return false;
  
  sheet.appendRow([item, quantity, category, addedBy, '', new Date()]);
  return true;
}

function processChores(ss, content, from) {
  const parts = content.split('|').map(p => p.trim());
  const task = parts[0] || content;
  const assignedTo = parts[1] || 'Anyone';
  const frequency = parts[2] || 'Weekly';
  const addedBy = extractName(from);
  
  const sheet = ss.getSheetByName('✅ Chores');
  if (!sheet) return false;
  
  sheet.appendRow([task, assignedTo, '', frequency, '', new Date()]);
  return true;
}

function processEvent(ss, content, from) {
  const parts = content.split('|').map(p => p.trim());
  const event = parts[0] || content;
  const dateStr = parts[1] || '';
  const time = parts[2] || 'All day';
  const who = parts[3] || 'Family';
  const location = parts[4] || '';
  
  // Try to parse the date
  let date = new Date();
  if (dateStr) {
    const dateParts = dateStr.split('/');
    if (dateParts.length === 3) {
      // DD/MM/YYYY format
      date = new Date(parseInt(dateParts[2]), parseInt(dateParts[1]) - 1, parseInt(dateParts[0]));
    } else {
      date = new Date(dateStr);
    }
  }
  
  const sheet = ss.getSheetByName('📅 Calendar');
  if (!sheet) return false;
  
  sheet.appendRow([formatDate(date), time, event, who, location, 'Added via email by ' + extractName(from)]);
  return true;
}

function processNews(ss, content, from) {
  const parts = content.split('|').map(p => p.trim());
  const message = parts[0] || content;
  const priority = parts[1] || 'Info';
  const fromName = extractName(from);
  
  const sheet = ss.getSheetByName('📝 Announcements');
  if (!sheet) return false;
  
  sheet.appendRow([formatDate(new Date()), fromName, message, priority]);
  return true;
}

function processContact(ss, content, from) {
  const parts = content.split('|').map(p => p.trim());
  const name = parts[0] || content;
  const phone = parts[1] || '';
  const email = parts[2] || '';
  const type = parts[3] || 'Other';
  const notes = parts[4] || '';
  
  const sheet = ss.getSheetByName('📞 Important Contacts');
  if (!sheet) return false;
  
  sheet.appendRow([name, type, phone, email, '', notes]);
  return true;
}

function processMeal(ss, content, from) {
  const parts = content.split('|').map(p => p.trim());
  const day = parts[0] || '';
  const meal = parts[1] || content;
  
  const sheet = ss.getSheetByName('🍽️ Meal Plan');
  if (!sheet) return false;
  
  sheet.appendRow([day, '', '', meal, 'Added via email by ' + extractName(from)]);
  return true;
}

// === HELPERS ===

function extractName(from) {
  // Extract name from "Name <email>" format
  const match = from.match(/^"?([^"<]+)"?\s*</);
  if (match) return match[1].trim();
  // Fallback: use email prefix
  const email = from.match(/<(.+)>/);
  if (email) return email[1].split('@')[0];
  return from;
}

function formatDate(d) {
  if (isNaN(d.getTime())) return '';
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Manual test function - run this first to verify it works
 */
function testProcessEmails() {
  Logger.log('Test: processEmails function exists and spreadsheet is accessible');
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  Logger.log('Spreadsheet: ' + ss.getName());
  Logger.log('Sheets: ' + ss.getSheets().map(s => s.getName()).join(', '));
  Logger.log('✅ Test passed! Set up the timer trigger to run processEmails every 5 minutes.');
}
