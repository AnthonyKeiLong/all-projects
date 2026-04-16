// =============================================================================
// =============================================================================
//
//   ⚠️  ABSENCE AUTOMATION SCRIPT  ⚠️
//
//   PURPOSE:
//   This script scans your attendance data sheet for students whose
//   Column N cell has a YELLOW background, extracts their absence info,
//   and writes it to a "need follow up" sheet. The user then fills in
//   teacher initials manually. The script groups students by class and
//   sends ONE email per class teacher.
//
//   THREE-STEP WORKFLOW:
//   Step 1: "Scan & Log" — finds yellow rows, writes them to
//           the "need follow up" sheet with a blank "教師縮寫" column.
//           Marks yellow cells GREEN. NO emails sent.
//           >>> The user then fills in teacher initials in the sheet. <<<
//   Step 2: "Prepare & Review Emails" — reads the "need follow up" sheet,
//           resolves initials to emails, builds a preview for review.
//   Step 3: "Send Prepared Emails" — sends the previewed emails.
//
//   EMAIL TEMPLATE:
//   Read from the "email template" sheet — edit directly in Google Sheets.
//
// =============================================================================
// =============================================================================


// =============================================================================
// ██████╗  ██████╗ ███╗   ██╗███████╗██╗ ██████╗ ██╗   ██╗██████╗ ███████╗
// ██╔════╝██╔═══██╗████╗  ██║██╔════╝██║██╔════╝ ██║   ██║██╔══██╗██╔════╝
// ██║     ██║   ██║██╔██╗ ██║█████╗  ██║██║  ███╗██║   ██║██████╔╝█████╗
// ██║     ██║   ██║██║╚██╗██║██╔══╝  ██║██║   ██║██║   ██║██╔══██╗██╔══╝
// ╚██████╗╚██████╔╝██║ ╚████║██║     ██║╚██████╔╝╚██████╔╝██║  ██║███████╗
//  ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝     ╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝
//
//  >>> EDIT THE SETTINGS BELOW TO MATCH YOUR SPREADSHEET <<<
//
// =============================================================================


// -----------------------------------------------------------------------------
// SETTING 1: DATA SHEET NAME (AUTO-DETECT)
// -----------------------------------------------------------------------------
// Add all possible sheet names below (past, present, future terms).
// The script will automatically find the first one that exists.
// If NONE exist, it will show a dropdown listing all sheets so you can pick.
//
// >>> Just add new names to this list each term — NO other code changes needed. <<<
// -----------------------------------------------------------------------------
var POSSIBLE_DATA_SHEETS = [
  "UT1", "UT2", "UT3",
  "Exam1", "Exam2",
  "SA1", "SA2",
  "T1", "T2", "T3"
  // Add more names here as needed, e.g. "Mid-term", "Final"
];


// -----------------------------------------------------------------------------
// SETTING 2: COLUMN MAPPING — STUDENT DATA
// -----------------------------------------------------------------------------
// Column A = 1, Column B = 2, Column C = 3, ... Column N = 14
// -----------------------------------------------------------------------------
var COL_DATE    = 1;   // 缺考日期 (Date of Absence)    — which column?
var COL_CLASS   = 2;   // 班別     (Class)               — which column?
var COL_ID      = 3;   // 學號     (Student ID)          — which column?
var COL_NAME    = 4;   // 姓名（中）(Chinese Name)       — which column?
var COL_SUBJECT = 5;   // 缺考科目  (Subject of Absence) — which column?
var COL_FLAG    = 14;  // The column with YELLOW highlight (default: N = 14)


// -----------------------------------------------------------------------------
// SETTING 3: EMAIL DOMAIN
// -----------------------------------------------------------------------------
// Appended to the teacher initials to form the email address.
// e.g., initials "abc" + domain "@keilong.edu.hk" → abc@keilong.edu.hk
// -----------------------------------------------------------------------------
var EMAIL_DOMAIN = "@keilong.edu.hk";


// -----------------------------------------------------------------------------
// SETTING 4: COLORS
// -----------------------------------------------------------------------------
var YELLOW_COLOR  = "#ffff00";   // Yellow background to detect
var GREEN_COLOR   = "#00ff00";   // Green = processed


// -----------------------------------------------------------------------------
// SETTING 5: SHEET NAMES
// -----------------------------------------------------------------------------
var FOLLOWUP_SHEET_NAME      = "need follow up";
var PREVIEW_SHEET_NAME       = "email preview";
var TEMPLATE_SHEET_NAME      = "email template";
var CLASS_TEACHER_SHEET_NAME = "class teacher list";


// =============================================================================
//
//  >>>  DO NOT EDIT BELOW THIS LINE UNLESS YOU KNOW WHAT YOU'RE DOING  <<<
//
// =============================================================================


// =============================================================================
//  "need follow up" sheet columns (0-based index for reading arrays)
//  A=缺考日期, B=班別, C=學號, D=姓名（中）, E=缺考科目,
//  F=教師縮寫 (user fills this in manually), G=狀態, H=處理時間
// =============================================================================
var FU_COL_DATE     = 0;  // Column A in "need follow up"
var FU_COL_CLASS    = 1;  // Column B
var FU_COL_ID       = 2;  // Column C
var FU_COL_NAME     = 3;  // Column D
var FU_COL_SUBJECT  = 4;  // Column E
var FU_COL_INITIALS = 5;  // Column F — teacher initials (user fills this in)
var FU_COL_STATUS   = 6;  // Column G — "PENDING" / "EMAILED"
var FU_COL_TIME     = 7;  // Column H — timestamp
var FU_TOTAL_COLS   = 8;  // Total columns in the follow-up sheet


// =============================================================================
//  AUTO-DETECT DATA SHEET
// =============================================================================
/**
 * Finds the data sheet by checking POSSIBLE_DATA_SHEETS in order.
 * If none match, shows a dropdown of all sheets for the user to pick.
 * Returns the Sheet object, or null if the user cancels.
 */
function resolveDataSheet_(spreadsheet) {
  // Try each name in the list
  for (var i = 0; i < POSSIBLE_DATA_SHEETS.length; i++) {
    var sheet = spreadsheet.getSheetByName(POSSIBLE_DATA_SHEETS[i]);
    if (sheet) {
      Logger.log('Auto-detected data sheet: "' + POSSIBLE_DATA_SHEETS[i] + '"');
      return sheet;
    }
  }

  // None matched — ask the user to pick from ALL sheets
  var ui = SpreadsheetApp.getUi();
  var allSheets = spreadsheet.getSheets();
  var skipNames = [FOLLOWUP_SHEET_NAME, PREVIEW_SHEET_NAME, TEMPLATE_SHEET_NAME, CLASS_TEACHER_SHEET_NAME];
  var candidates = [];
  for (var j = 0; j < allSheets.length; j++) {
    var name = allSheets[j].getName();
    if (skipNames.indexOf(name) === -1) {
      candidates.push(name);
    }
  }

  if (candidates.length === 0) {
    ui.alert('❌ ERROR: No data sheets found in this spreadsheet.');
    return null;
  }

  if (candidates.length === 1) {
    // Only one candidate — use it directly
    Logger.log('Only one candidate sheet: "' + candidates[0] + '"');
    return spreadsheet.getSheetByName(candidates[0]);
  }

  // Multiple candidates — ask user
  var prompt = 'Could not auto-detect the data sheet.\n\n' +
    'Available sheets:\n';
  for (var k = 0; k < candidates.length; k++) {
    prompt += '  ' + (k + 1) + '. ' + candidates[k] + '\n';
  }
  prompt += '\nType the sheet name exactly:';

  var response = ui.prompt('📋 Select Data Sheet', prompt, ui.ButtonSet.OK_CANCEL);
  if (response.getSelectedButton() !== ui.Button.OK) {
    return null;
  }

  var chosen = response.getResponseText().trim();
  var chosenSheet = spreadsheet.getSheetByName(chosen);
  if (!chosenSheet) {
    ui.alert('❌ ERROR: Cannot find sheet "' + chosen + '". Check spelling and try again.');
    return null;
  }
  return chosenSheet;
}


/**
 * onOpen() — adds the custom menu to the spreadsheet toolbar.
 * Runs automatically every time the spreadsheet is opened.
 *
 * ⚠️ NOTE: Do NOT run this from the Apps Script editor's ▶ button.
 *    It only works when the spreadsheet is opened in the browser.
 *    If you need to manually re-create the menu, use installMenu() below.
 */
function onOpen() {
  try {
    createCustomMenu_();
  } catch (e) {
    // SpreadsheetApp.getUi() is not available when run from the script editor.
    // This is normal — the menu will appear when the spreadsheet is opened.
    Logger.log('onOpen: Could not create menu (this is normal if run from the editor). ' + e.message);
  }
}


/**
 * installMenu() — manually re-creates the custom menu.
 * Run this from the script editor if the menu didn't appear,
 * or call it after making changes to menu items.
 */
function installMenu() {
  createCustomMenu_();
}


/**
 * createCustomMenu_() — the actual menu-building logic, used by both
 * onOpen() and installMenu().
 */
function createCustomMenu_() {
  var ui = SpreadsheetApp.getUi();

  ui.createMenu('⚠️ Absence Automation')

    // Step 1: Scan yellow → write to "need follow up" → mark green
    .addItem('Step 1 ▶ Scan & Log Absences', 'runStep1_ScanAndLog')

    .addSeparator()

    // Step 2: Read follow-up sheet (with user-entered initials) → build preview
    .addItem('Step 2 📋 Prepare & Review Emails', 'runStep2_PrepareAndReview')

    .addSeparator()

    // Step 3: Send from preview sheet
    .addItem('Step 3 ✉ Send Prepared Emails', 'runStep3_SendEmails')

    .addSeparator()

    // Utility: create/reset template sheet
    .addItem('📝 Create / Reset Email Template Sheet', 'createTemplateSheet')

    .addSeparator()

    // Utility: create class teacher list
    .addItem('👨‍🏫 Create / View Class Teacher List', 'createClassTeacherSheet')

    .addToUi();
}


// =============================================================================
//  STEP 1 — SCAN & LOG (no emails, no initials needed yet)
// =============================================================================
/**
 * Scans the data sheet for yellow-highlighted rows in the flag column.
 * Writes them to the "need follow up" sheet with a blank teacher initials
 * column and status "PENDING". Marks yellow cells green.
 *
 * After this, the user manually types teacher initials in the "need follow up"
 * sheet's "教師縮寫" column, then runs Step 2.
 */
function runStep1_ScanAndLog() {
  var ui = SpreadsheetApp.getUi();
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();

  // --- Confirmation ---
  var confirmation = ui.alert(
    '📋 Step 1: Scan & Log',
    'This will:\n' +
    '1. Scan for yellow rows in Column ' + columnLetterFromNumber_(COL_FLAG) + '\n' +
    '2. Write them to the "' + FOLLOWUP_SHEET_NAME + '" sheet\n' +
    '3. Mark processed yellow cells GREEN\n\n' +
    '⚠️ NO emails will be sent.\n' +
    'After this, you will fill in teacher initials in the "' + FOLLOWUP_SHEET_NAME + '" sheet.\n\n' +
    'Continue?',
    ui.ButtonSet.YES_NO
  );

  if (confirmation !== ui.Button.YES) {
    ui.alert('❌ Aborted.');
    return;
  }

  // --- Open data sheet (auto-detect) ---
  var dataSheet = resolveDataSheet_(spreadsheet);
  if (!dataSheet) return;

  var lastRow = dataSheet.getLastRow();
  if (lastRow < 2) {
    ui.alert('ℹ️ No data found (sheet is empty or only has headers).');
    return;
  }

  // --- Read data and backgrounds in one batch ---
  var maxCol = Math.max(dataSheet.getLastColumn(), COL_FLAG);
  var dataRange = dataSheet.getRange(2, 1, lastRow - 1, maxCol);
  var data = dataRange.getValues();
  var backgrounds = dataRange.getBackgrounds();

  // --- Find yellow rows ---
  var flaggedStudents = [];
  var yellowRowNumbers = [];

  for (var i = 0; i < data.length; i++) {
    var bgColor = backgrounds[i][COL_FLAG - 1].toLowerCase();

    if (bgColor === YELLOW_COLOR) {
      flaggedStudents.push({
        date:    formatCellValue_(data[i][COL_DATE - 1]),
        class_:  formatCellValue_(data[i][COL_CLASS - 1]),
        id:      formatCellValue_(data[i][COL_ID - 1]),
        name:    formatCellValue_(data[i][COL_NAME - 1]),
        subject: formatCellValue_(data[i][COL_SUBJECT - 1])
      });
      yellowRowNumbers.push(i + 2);
    }
  }

  if (flaggedStudents.length === 0) {
    ui.alert('ℹ️ No yellow rows found in Column ' +
             columnLetterFromNumber_(COL_FLAG) + '.');
    return;
  }

  // --- Load class teacher lookup ---
  var teacherMap = loadClassTeacherMap_(spreadsheet);
  var autoFilled = 0;
  var notFound = [];

  // --- Write to "need follow up" sheet ---
  var followUpSheet = getOrCreateFollowUpSheet_(spreadsheet);
  var nextRow = followUpSheet.getLastRow() + 1;
  var timestamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');

  var outputData = [];
  for (var j = 0; j < flaggedStudents.length; j++) {
    var s = flaggedStudents[j];
    // Auto-fill initials from class teacher list (if available)
    var initials = '';
    if (teacherMap && teacherMap[s.class_]) {
      initials = teacherMap[s.class_];
      autoFilled++;
    } else if (teacherMap) {
      if (notFound.indexOf(s.class_) === -1) notFound.push(s.class_);
    }
    // Columns: 缺考日期 | 班別 | 學號 | 姓名（中） | 缺考科目 | 教師縮寫 | 狀態 | 處理時間
    outputData.push([s.date, s.class_, s.id, s.name, s.subject, initials, 'PENDING', timestamp]);
  }

  followUpSheet.getRange(nextRow, 1, outputData.length, FU_TOTAL_COLS)
    .setValues(outputData);

  // Highlight rows that still need manual initials
  for (var n = 0; n < outputData.length; n++) {
    if (!outputData[n][FU_COL_INITIALS]) {
      followUpSheet.getRange(nextRow + n, FU_COL_INITIALS + 1)
        .setBackground('#fff9c4');  // light yellow = "please fill me in"
    }
  }

  // --- Mark yellow cells green in data sheet ---
  for (var m = 0; m < yellowRowNumbers.length; m++) {
    dataSheet.getRange(yellowRowNumbers[m], COL_FLAG).setBackground(GREEN_COLOR);
  }
  SpreadsheetApp.flush();

  // --- Switch to the follow-up sheet ---
  spreadsheet.setActiveSheet(followUpSheet);

  Logger.log('📝 Step 1: Logged ' + flaggedStudents.length + ' rows. Marked green.');

  // --- Summary ---
  var summaryText = 'Yellow rows found and logged: ' + flaggedStudents.length + '\n' +
    'Data written to "' + FOLLOWUP_SHEET_NAME + '" sheet.\n' +
    'Processed rows marked GREEN in "' + dataSheet.getName() + '".\n\n';

  if (teacherMap) {
    summaryText += '👨‍🏫 Teacher initials auto-filled: ' + autoFilled + ' / ' + flaggedStudents.length + '\n';
    if (notFound.length > 0) {
      summaryText += '⚠️ Classes NOT found in "' + CLASS_TEACHER_SHEET_NAME + '": ' + notFound.join(', ') + '\n' +
        'Please fill in their initials manually in Column F.\n\n';
    }
  } else {
    summaryText += 'ℹ️ No "' + CLASS_TEACHER_SHEET_NAME + '" sheet found — initials left blank.\n' +
      'Create one via: ⚠️ Absence Automation → 👨‍🏫 Create / View Class Teacher List\n\n';
  }

  summaryText += '📋 NEXT:\n' +
    '1. Go to the "' + FOLLOWUP_SHEET_NAME + '" sheet (now open)\n' +
    '2. Review / fill in the "教師縮寫 (Initials)" column (Column F)\n' +
    '   — Use "/" for two teachers, e.g., "lsk/ mky"\n' +
    '   — The script will add "' + EMAIL_DOMAIN + '" automatically\n' +
    '3. Then click:\n' +
    '   ⚠️ Absence Automation → Step 2 📋 Prepare & Review Emails';

  ui.alert('✅ Step 1 Complete', summaryText, ui.ButtonSet.OK);
}


// =============================================================================
//  STEP 2 — PREPARE & REVIEW EMAILS
// =============================================================================
/**
 * Reads the "need follow up" sheet for rows with status "PENDING" that
 * have teacher initials filled in. Groups by class, builds email previews
 * using the template sheet, writes to the "email preview" sheet.
 * NO emails are sent.
 */
function runStep2_PrepareAndReview() {
  var ui = SpreadsheetApp.getUi();
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();

  // --- Check that "need follow up" sheet exists ---
  var followUpSheet = spreadsheet.getSheetByName(FOLLOWUP_SHEET_NAME);
  if (!followUpSheet) {
    ui.alert('❌ ERROR: No "' + FOLLOWUP_SHEET_NAME + '" sheet found.\n\n' +
             'Please run Step 1 first.');
    return;
  }

  var fuLastRow = followUpSheet.getLastRow();
  if (fuLastRow < 2) {
    ui.alert('ℹ️ No data in "' + FOLLOWUP_SHEET_NAME + '". Run Step 1 first.');
    return;
  }

  // --- Read email template ---
  var template = readEmailTemplate_(spreadsheet);
  if (!template) return; // error already shown

  // --- Read all rows from follow-up sheet ---
  var fuData = followUpSheet.getRange(2, 1, fuLastRow - 1, FU_TOTAL_COLS).getValues();

  // --- Find PENDING rows with initials filled in ---
  var pendingStudents = [];    // students ready to email
  var missingInitials = [];    // rows that still need initials

  for (var i = 0; i < fuData.length; i++) {
    var status = String(fuData[i][FU_COL_STATUS]).trim().toUpperCase();
    if (status !== 'PENDING') continue;

    var initials = String(fuData[i][FU_COL_INITIALS]).trim().toLowerCase();

    if (!initials) {
      // Row is PENDING but has no initials — track it but skip
      var rowNum = i + 2;
      missingInitials.push('Row ' + rowNum + ': ' +
        fuData[i][FU_COL_NAME] + ' (' + fuData[i][FU_COL_CLASS] + ')');
      continue;
    }

    pendingStudents.push({
      fuRowIndex: i,               // index in the follow-up data (for later reference)
      date:      formatCellValue_(fuData[i][FU_COL_DATE]),
      class_:    formatCellValue_(fuData[i][FU_COL_CLASS]),
      id:        formatCellValue_(fuData[i][FU_COL_ID]),
      name:      formatCellValue_(fuData[i][FU_COL_NAME]),
      subject:   formatCellValue_(fuData[i][FU_COL_SUBJECT]),
      initials:  initials,
      email:     resolveEmails_(initials)
    });
  }

  if (pendingStudents.length === 0 && missingInitials.length === 0) {
    ui.alert('ℹ️ No PENDING rows found in "' + FOLLOWUP_SHEET_NAME + '".\n\n' +
             'All rows have already been emailed, or you need to run Step 1 first.');
    return;
  }

  if (pendingStudents.length === 0 && missingInitials.length > 0) {
    ui.alert('⚠️ Found ' + missingInitials.length + ' PENDING row(s), but none have ' +
             'teacher initials filled in.\n\n' +
             'Please fill in the "教師縮寫 (Initials)" column (F) in the "' +
             FOLLOWUP_SHEET_NAME + '" sheet, then run Step 2 again.\n\n' +
             'Missing initials:\n' + missingInitials.slice(0, 10).join('\n') +
             (missingInitials.length > 10 ? '\n... and ' + (missingInitials.length - 10) + ' more' : ''));
    return;
  }

  // --- Confirmation ---
  var confirmMsg = 'Found ' + pendingStudents.length + ' student(s) ready to email.\n';
  if (missingInitials.length > 0) {
    confirmMsg += '⚠️ ' + missingInitials.length + ' row(s) still missing initials (will be skipped).\n';
  }
  confirmMsg += '\nThis will build an email preview for your review.\n' +
                'NO emails will be sent yet.\n\nContinue?';

  var confirmation = ui.alert('📋 Step 2: Prepare Emails', confirmMsg, ui.ButtonSet.YES_NO);
  if (confirmation !== ui.Button.YES) {
    ui.alert('❌ Aborted.');
    return;
  }

  // --- Group students by class ---
  var classBuckets = {};
  for (var j = 0; j < pendingStudents.length; j++) {
    var student = pendingStudents[j];
    var cls = student.class_;
    if (!classBuckets[cls]) {
      classBuckets[cls] = [];
    }
    classBuckets[cls].push(student);
  }

  // --- Build email preview ---
  var previewSheet = getOrCreatePreviewSheet_(spreadsheet);

  // Clear old preview data (keep header row)
  var previewLastRow = previewSheet.getLastRow();
  if (previewLastRow > 1) {
    previewSheet.getRange(2, 1, previewLastRow - 1, 7).clearContent();
    previewSheet.getRange(2, 1, previewLastRow - 1, 7).clearFormat();
  }

  var classNames = Object.keys(classBuckets).sort();
  var previewRows = [];
  var today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');

  for (var k = 0; k < classNames.length; k++) {
    var className = classNames[k];
    var students = classBuckets[className];

    // Use teacher email from the first student (same class = same teacher)
    var teacherInitials = students[0].initials;
    var teacherEmail = students[0].email;

    // Build the student table for the email body
    var studentTable = buildStudentTable_(students);

    // Fill template placeholders
    var emailSubject = template.subject
      .replace(/\{\{CLASS\}\}/g, className)
      .replace(/\{\{COUNT\}\}/g, String(students.length))
      .replace(/\{\{TODAY\}\}/g, today);

    var emailBody = template.body
      .replace(/\{\{CLASS\}\}/g, className)
      .replace(/\{\{STUDENT_TABLE\}\}/g, studentTable)
      .replace(/\{\{COUNT\}\}/g, String(students.length))
      .replace(/\{\{TODAY\}\}/g, today);

    // Collect the follow-up row numbers for this class (so Step 3 can update them)
    var fuRowNums = [];
    for (var s = 0; s < students.length; s++) {
      fuRowNums.push(students[s].fuRowIndex + 2); // convert 0-based to sheet row
    }

    // Preview row: Class | Initials | Email | Subject | Body | Status | FollowUpRows (hidden helper)
    previewRows.push([
      className,
      teacherInitials,
      teacherEmail,
      emailSubject,
      emailBody,
      'PENDING',
      fuRowNums.join(',')  // comma-separated list of row numbers to mark as EMAILED
    ]);
  }

  // Write preview rows
  if (previewRows.length > 0) {
    previewSheet.getRange(2, 1, previewRows.length, previewRows[0].length)
      .setValues(previewRows);
  }

  // Switch to preview sheet
  spreadsheet.setActiveSheet(previewSheet);

  // --- Summary ---
  var summaryMsg = '✅ Step 2 Complete!\n\n' +
    'Students ready: ' + pendingStudents.length + '\n' +
    'Classes: ' + classNames.join(', ') + '\n' +
    'Emails prepared: ' + previewRows.length + '\n';

  if (missingInitials.length > 0) {
    summaryMsg += '\n⚠️ Skipped ' + missingInitials.length +
      ' row(s) with missing initials.\n';
  }

  summaryMsg += '\n📋 NEXT:\n' +
    '1. Review the "' + PREVIEW_SHEET_NAME + '" sheet (now open)\n' +
    '2. Double-check teacher email addresses in the "教師電郵" column\n' +
    '3. You can EDIT emails directly in the preview if needed\n' +
    '4. When satisfied, click:\n' +
    '   ⚠️ Absence Automation → Step 3 ✉ Send Prepared Emails';

  ui.alert('📋 Step 2: Preview Ready', summaryMsg, ui.ButtonSet.OK);
}


// =============================================================================
//  STEP 3 — SEND PREPARED EMAILS
// =============================================================================
/**
 * Reads the "email preview" sheet and sends all emails marked "PENDING".
 * Updates status to "SENT" in the preview sheet and "EMAILED" in the
 * "need follow up" sheet.
 */
function runStep3_SendEmails() {
  var ui = SpreadsheetApp.getUi();
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();

  // --- Check preview sheet ---
  var previewSheet = spreadsheet.getSheetByName(PREVIEW_SHEET_NAME);
  if (!previewSheet) {
    ui.alert('❌ ERROR: No "' + PREVIEW_SHEET_NAME + '" sheet found.\n\n' +
             'Please run Step 1 and Step 2 first.');
    return;
  }

  var previewLastRow = previewSheet.getLastRow();
  if (previewLastRow < 2) {
    ui.alert('ℹ️ No prepared emails. Run Step 2 first.');
    return;
  }

  var previewData = previewSheet.getRange(2, 1, previewLastRow - 1, 7).getValues();

  // Count pending emails
  var pendingCount = 0;
  var pendingList = '';
  for (var i = 0; i < previewData.length; i++) {
    var status = String(previewData[i][5]).trim().toUpperCase();
    if (status === 'PENDING') {
      pendingCount++;
      pendingList += '  • ' + previewData[i][0] + ' → ' + previewData[i][2] + '\n';
    }
  }

  if (pendingCount === 0) {
    ui.alert('ℹ️ No PENDING emails found.\n\n' +
             'All emails have been sent, or run Step 2 to prepare new ones.');
    return;
  }

  // --- Final confirmation ---
  var confirmation = ui.alert(
    '✉ Step 3: Confirm Send',
    'Sending ' + pendingCount + ' email(s) to:\n\n' +
    pendingList + '\n' +
    '⚠️ This cannot be undone. Continue?',
    ui.ButtonSet.YES_NO
  );

  if (confirmation !== ui.Button.YES) {
    ui.alert('❌ Aborted. No emails sent.');
    return;
  }

  // --- Send emails ---
  var followUpSheet = spreadsheet.getSheetByName(FOLLOWUP_SHEET_NAME);
  var sent = 0;
  var failed = [];

  for (var j = 0; j < previewData.length; j++) {
    var row = previewData[j];
    var emailStatus = String(row[5]).trim().toUpperCase();
    if (emailStatus !== 'PENDING') continue;

    var className    = String(row[0]).trim();
    var teacherEmail = String(row[2]).trim();
    var emailSubject = String(row[3]);
    var emailBody    = String(row[4]);
    var fuRowNums    = String(row[6]);  // comma-separated follow-up row numbers

    // Validate email
    if (!teacherEmail || teacherEmail.indexOf('@') === -1) {
      previewSheet.getRange(j + 2, 6).setValue('SKIPPED — no valid email');
      failed.push(className + ' (no email)');
      continue;
    }

    // Send
    try {
      MailApp.sendEmail(teacherEmail, emailSubject, emailBody);

      // Mark SENT in preview
      var sentTimestamp = Utilities.formatDate(
        new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');
      previewSheet.getRange(j + 2, 6).setValue('SENT ✅ ' + sentTimestamp);

      // Mark EMAILED in "need follow up" sheet
      if (followUpSheet && fuRowNums) {
        var rowNums = fuRowNums.split(',');
        for (var r = 0; r < rowNums.length; r++) {
          var fuRow = parseInt(rowNums[r], 10);
          if (fuRow >= 2) {
            // Update status column (G) to "EMAILED"
            followUpSheet.getRange(fuRow, FU_COL_STATUS + 1).setValue('EMAILED ✅');
          }
        }
      }

      sent++;
      Logger.log('✅ Sent to ' + teacherEmail + ' for ' + className);

    } catch (e) {
      previewSheet.getRange(j + 2, 6).setValue('FAILED ❌ ' + e.message);
      failed.push(className + ' (' + e.message + ')');
      Logger.log('❌ Failed: ' + teacherEmail + ' — ' + e.message);
    }
  }

  SpreadsheetApp.flush();

  // --- Summary ---
  var summaryMsg = 'Emails sent: ' + sent + '\n';
  if (failed.length > 0) {
    summaryMsg += '\n⚠️ Skipped/Failed:\n' + failed.join('\n');
  }

  ui.alert('✉ Step 3 Complete', summaryMsg, ui.ButtonSet.OK);
}


// =============================================================================
//  EMAIL TEMPLATE SHEET — Create / Reset
// =============================================================================
/**
 * Creates (or resets) the "email template" sheet with a default template.
 * User edits B2 (subject) and B3 (body) directly in the spreadsheet.
 *
 * Placeholders: {{CLASS}}, {{STUDENT_TABLE}}, {{COUNT}}, {{TODAY}}
 */
function createTemplateSheet() {
  var ui = SpreadsheetApp.getUi();
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  var existing = spreadsheet.getSheetByName(TEMPLATE_SHEET_NAME);

  if (existing) {
    var confirm = ui.alert(
      '⚠️ Sheet Already Exists',
      'Reset "' + TEMPLATE_SHEET_NAME + '" to the default template?\n' +
      '(Your current template will be overwritten)',
      ui.ButtonSet.YES_NO
    );
    if (confirm !== ui.Button.YES) {
      ui.alert('❌ Cancelled.');
      return;
    }
    existing.clear();
  }

  var sheet = existing || spreadsheet.insertSheet(TEMPLATE_SHEET_NAME);

  // Row 1: Headers
  sheet.getRange(1, 1).setValue('Setting');
  sheet.getRange(1, 2).setValue('Value');
  sheet.getRange(1, 1, 1, 2).setFontWeight('bold').setBackground('#4a86c8').setFontColor('#ffffff');

  // Row 2: Subject
  sheet.getRange(2, 1).setValue('Subject');
  sheet.getRange(2, 2).setValue('⚠️ 缺考跟進通知 — {{CLASS}}');

  // Row 3: Body
  sheet.getRange(3, 1).setValue('Body');
  sheet.getRange(3, 2).setValue(
    '敬啟者，\n\n' +
    '以下為 {{CLASS}} 班需要跟進的缺考學生名單（共 {{COUNT}} 位）：\n\n' +
    '{{STUDENT_TABLE}}\n\n' +
    '請協助跟進上述學生的缺考事宜。\n\n' +
    '此電郵由系統自動發出，日期：{{TODAY}}\n' +
    '如有疑問，請聯繫考試組。\n\n' +
    '謝謝！'
  );

  // Instructions
  sheet.getRange(5, 1).setValue('📖 Instructions');
  sheet.getRange(5, 1).setFontWeight('bold');
  sheet.getRange(6, 1, 1, 2).merge();
  sheet.getRange(6, 1).setValue(
    'Edit the Subject (B2) and Body (B3) above.\n\n' +
    'Placeholders (replaced automatically):\n' +
    '  {{CLASS}}         → Class name (e.g., "1A")\n' +
    '  {{STUDENT_TABLE}} → Formatted student list\n' +
    '  {{COUNT}}         → Number of students\n' +
    '  {{TODAY}}         → Today\'s date (YYYY-MM-DD)\n\n' +
    'Line breaks: type \\n or press Alt+Enter inside the cell.\n\n' +
    '⚠️ Do NOT rename or reorder cells. B2 = Subject, B3 = Body.'
  );
  sheet.getRange(6, 1).setWrap(true);

  // Formatting
  sheet.setColumnWidth(1, 120);
  sheet.setColumnWidth(2, 600);
  sheet.getRange(2, 2).setWrap(true).setBackground('#fff9c4');
  sheet.getRange(3, 2).setWrap(true).setBackground('#fff9c4');
  sheet.setRowHeight(3, 200);

  spreadsheet.setActiveSheet(sheet);

  ui.alert('✅ Template sheet created!',
    'Edit the yellow cells:\n' +
    '  • B2 = Email Subject\n' +
    '  • B3 = Email Body\n\n' +
    'Placeholders: {{CLASS}}, {{STUDENT_TABLE}}, {{COUNT}}, {{TODAY}}',
    ui.ButtonSet.OK);
}


// =============================================================================
//  CLASS TEACHER LIST — Create / View
// =============================================================================
/**
 * Creates the "class teacher list" sheet with example data.
 * User fills in: Column A = Class, Column B = Teacher Initials.
 * Use "/" for two class teachers, e.g. "lsk/ mky".
 */
function createClassTeacherSheet() {
  var ui = SpreadsheetApp.getUi();
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  var existing = spreadsheet.getSheetByName(CLASS_TEACHER_SHEET_NAME);

  if (existing) {
    spreadsheet.setActiveSheet(existing);
    ui.alert('👨‍🏫 Class Teacher List',
      'Sheet "' + CLASS_TEACHER_SHEET_NAME + '" already exists.\n\n' +
      'Edit Column A (班別) and Column B (教師縮寫) as needed.\n' +
      'Use "/" for two teachers, e.g. "lsk/ mky".',
      ui.ButtonSet.OK);
    return;
  }

  var sheet = spreadsheet.insertSheet(CLASS_TEACHER_SHEET_NAME);

  // Headers
  sheet.getRange(1, 1).setValue('班別 (Class)');
  sheet.getRange(1, 2).setValue('教師縮寫 (Initials)');
  sheet.getRange(1, 1, 1, 2).setFontWeight('bold').setBackground('#4a86c8').setFontColor('#ffffff');
  sheet.setFrozenRows(1);

  // Example data — replace with your actual classes
  var examples = [
    ['1A', 'abc'],
    ['1B', 'def/ ghi'],
    ['2A', 'lsk/ mky'],
    ['2B', 'cts/ tcy'],
    ['3A', 'lhyu/ lhl']
  ];
  sheet.getRange(2, 1, examples.length, 2).setValues(examples);
  sheet.getRange(2, 1, examples.length, 2).setBackground('#fff9c4');

  // Instructions
  sheet.getRange(examples.length + 3, 1).setValue('📖 Instructions');
  sheet.getRange(examples.length + 3, 1).setFontWeight('bold');
  sheet.getRange(examples.length + 4, 1, 1, 2).merge();
  sheet.getRange(examples.length + 4, 1).setValue(
    'Fill in each class and its class teacher(s) initials.\n' +
    'Use "/" to separate two teachers, e.g. "lsk/ mky".\n' +
    'The class name must match EXACTLY what appears in your data sheet.\n' +
    'Step 1 will auto-fill the initials when scanning absences.'
  );
  sheet.getRange(examples.length + 4, 1).setWrap(true);

  sheet.setColumnWidth(1, 120);
  sheet.setColumnWidth(2, 200);

  spreadsheet.setActiveSheet(sheet);

  ui.alert('✅ Class Teacher List Created!',
    'Replace the example data with your actual class teachers.\n\n' +
    '  Column A = Class name (must match data sheet exactly)\n' +
    '  Column B = Teacher initials (use "/" for two teachers)\n\n' +
    'Step 1 will auto-fill initials from this list.',
    ui.ButtonSet.OK);
}


// =============================================================================
//  HELPER — Load class → teacher initials map
// =============================================================================
/**
 * Reads the "class teacher list" sheet and returns a map:
 *   { "2A": "lsk/ mky", "2B": "cts/ tcy", ... }
 * Returns null if the sheet doesn't exist.
 */
function loadClassTeacherMap_(spreadsheet) {
  var sheet = spreadsheet.getSheetByName(CLASS_TEACHER_SHEET_NAME);
  if (!sheet) return null;

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return {};

  var data = sheet.getRange(2, 1, lastRow - 1, 2).getValues();
  var map = {};
  for (var i = 0; i < data.length; i++) {
    var cls = String(data[i][0]).trim();
    var initials = String(data[i][1]).trim();
    if (cls && initials) {
      map[cls] = initials;
    }
  }
  return map;
}


// =============================================================================
//  HELPER — Resolve teacher initials to email(s)
// =============================================================================
/**
 * Takes a raw initials string (e.g. "lsk/ mky" or "abc")
 * and returns a comma-separated list of email addresses.
 * Splits on "/" so "lsk/ mky" → "lsk@keilong.edu.hk, mky@keilong.edu.hk"
 */
function resolveEmails_(rawInitials) {
  var parts = rawInitials.split('/');
  var emails = [];
  for (var i = 0; i < parts.length; i++) {
    var trimmed = parts[i].trim().toLowerCase();
    if (trimmed) {
      emails.push(trimmed + EMAIL_DOMAIN);
    }
  }
  return emails.join(', ');
}


// =============================================================================
//  HELPER — Read email template
// =============================================================================
function readEmailTemplate_(spreadsheet) {
  var templateSheet = spreadsheet.getSheetByName(TEMPLATE_SHEET_NAME);

  if (!templateSheet) {
    SpreadsheetApp.getUi().alert(
      '❌ Missing Email Template',
      'No "' + TEMPLATE_SHEET_NAME + '" sheet found.\n\n' +
      'Click: ⚠️ Absence Automation → 📝 Create / Reset Email Template Sheet\n' +
      'Then edit and run again.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return null;
  }

  var subject = templateSheet.getRange(2, 2).getValue();
  var body = templateSheet.getRange(3, 2).getValue();

  if (!subject || !body) {
    SpreadsheetApp.getUi().alert(
      '⚠️ Empty Template',
      'Subject (B2) or Body (B3) in "' + TEMPLATE_SHEET_NAME + '" is empty.\n' +
      'Please fill them in and try again.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return null;
  }

  return { subject: String(subject), body: String(body) };
}


// =============================================================================
//  HELPER — Get or create "need follow up" sheet
// =============================================================================
function getOrCreateFollowUpSheet_(spreadsheet) {
  var sheet = spreadsheet.getSheetByName(FOLLOWUP_SHEET_NAME);

  if (!sheet) {
    sheet = spreadsheet.insertSheet(FOLLOWUP_SHEET_NAME);
  }

  // Always ensure headers are correct
  var headers = [
    '缺考日期',
    '班別',
    '學號',
    '姓名（中）',
    '缺考科目',
    '教師縮寫 (Initials)',
    '狀態 (Status)',
    '處理時間'
  ];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length)
    .setFontWeight('bold')
    .setBackground('#4a86c8')
    .setFontColor('#ffffff');
  sheet.setFrozenRows(1);

  // Column widths
  sheet.setColumnWidth(1, 100);  // Date
  sheet.setColumnWidth(2, 60);   // Class
  sheet.setColumnWidth(3, 60);   // ID
  sheet.setColumnWidth(4, 100);  // Name
  sheet.setColumnWidth(5, 100);  // Subject
  sheet.setColumnWidth(6, 140);  // Initials — this is where user types
  sheet.setColumnWidth(7, 120);  // Status
  sheet.setColumnWidth(8, 160);  // Timestamp

  return sheet;
}


// =============================================================================
//  HELPER — Get or create "email preview" sheet
// =============================================================================
function getOrCreatePreviewSheet_(spreadsheet) {
  var sheet = spreadsheet.getSheetByName(PREVIEW_SHEET_NAME);

  if (!sheet) {
    sheet = spreadsheet.insertSheet(PREVIEW_SHEET_NAME);
  }

  var headers = [
    '班別 (Class)',
    '教師縮寫 (Initials)',
    '教師電郵 (Email)',
    '主旨 (Subject)',
    '內容 (Body)',
    '狀態 (Status)',
    '(系統用 — 勿改)'  // internal: follow-up row numbers
  ];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length)
    .setFontWeight('bold')
    .setBackground('#4a86c8')
    .setFontColor('#ffffff');
  sheet.setFrozenRows(1);

  sheet.setColumnWidth(1, 80);
  sheet.setColumnWidth(2, 120);
  sheet.setColumnWidth(3, 220);
  sheet.setColumnWidth(4, 280);
  sheet.setColumnWidth(5, 500);
  sheet.setColumnWidth(6, 180);
  sheet.setColumnWidth(7, 130);

  return sheet;
}


// =============================================================================
//  HELPER — Build student table for email body
// =============================================================================
function buildStudentTable_(students) {
  var header = '  #  | 缺考日期       | 學號   | 姓名（中）   | 缺考科目\n';
  header    += '  ---|----------------|--------|-------------|----------\n';

  var rows = '';
  for (var i = 0; i < students.length; i++) {
    var s = students[i];
    var num = padRight_(String(i + 1), 3);
    rows += '  ' + num + '| ' + padRight_(s.date, 15) +
            '| ' + padRight_(s.id, 7) +
            '| ' + padRight_(s.name, 12) +
            '| ' + s.subject + '\n';
  }

  return header + rows;
}


// =============================================================================
//  HELPER — Format cell value to string
// =============================================================================
function formatCellValue_(value) {
  if (value === null || value === undefined || value === '') return '';
  if (value instanceof Date) {
    return Utilities.formatDate(value, Session.getScriptTimeZone(), 'yyyy-MM-dd');
  }
  return String(value).trim();
}


// =============================================================================
//  HELPER — Pad string to minimum width
// =============================================================================
function padRight_(str, width) {
  if (str.length >= width) return str;
  return str + new Array(width - str.length + 1).join(' ');
}


// =============================================================================
//  HELPER — Column number to letter (e.g., 14 → "N")
// =============================================================================
function columnLetterFromNumber_(colNum) {
  var letter = '';
  while (colNum > 0) {
    var remainder = (colNum - 1) % 26;
    letter = String.fromCharCode(65 + remainder) + letter;
    colNum = Math.floor((colNum - 1) / 26);
  }
  return letter;
}
