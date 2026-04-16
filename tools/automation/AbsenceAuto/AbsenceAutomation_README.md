# ⚠️ Absence Automation — Setup Guide
### Google Sheets + Gmail | 缺考自動通知系統

---

## What Does This Script Do?

1. **Scans** your data sheet for rows where Column N is **yellow**
2. **Logs** them to a **"need follow up"** sheet
3. **Auto-fills** class teacher initials from a **"class teacher list"** sheet (if set up)
4. The script **resolves emails** (initials + `@keilong.edu.hk`) and builds a **preview**
5. You **review** the preview, then confirm to **send** — one email per class teacher
6. Yellow cells turn **green** (won't be processed again)

---

## Three-Step Workflow

| Step | Menu Item | What Happens |
|------|-----------|--------------|
| **Step 1** | Scan & Log Absences | Finds yellow rows → writes to "need follow up" → auto-fills teacher initials → marks green. **No emails.** |
| *(You)* | *(Review initials)* | Check column F — fix or fill in any missing initials |
| **Step 2** | Prepare & Review Emails | Reads initials → resolves emails → builds preview. **No emails.** |
| **Step 3** | Send Prepared Emails | Sends emails from the preview. Updates status to "EMAILED". |

---

## Setup

### 1. Open Apps Script Editor
- Open your Google Spreadsheet → **Extensions** → **Apps Script**

### 2. Paste the Code
- Delete everything in the editor (or in a single `.gs` file)
- Copy all contents of `AbsenceAutomation.gs` → paste → **Save** (Ctrl+S)
- ⚠️ Make sure you only have **ONE** `.gs` file with this code (delete any duplicates like `Code.gs`)

### 3. Configure Settings (top of the script)

| Setting | What to Change |
|---------|---------------|
| `POSSIBLE_DATA_SHEETS` | List of possible data tab names (e.g., `"UT1", "UT2", "Exam1"`) — the script auto-detects which one exists |
| `COL_DATE` ... `COL_SUBJECT` | Column numbers for each field (A=1, B=2, ...) |
| `COL_FLAG` | Yellow-highlight column (default: N = 14) |
| `EMAIL_DOMAIN` | School email domain (default: `"@keilong.edu.hk"`) |
| `YELLOW_COLOR` | Hex code of your yellow (default: `"#ffff00"`) |

> **Note:** You do NOT need to change `POSSIBLE_DATA_SHEETS` each term — just add all expected names once (e.g., `"UT1", "UT2", "UT3", "Exam1", "Exam2"`). The script finds whichever one exists. If none match, it prompts you to pick from a list.

### 4. Save, Refresh, Set Up Sheets
1. Save the script
2. Refresh the spreadsheet (F5)
3. Wait for the **⚠️ Absence Automation** menu to appear
4. Click **📝 Create / Reset Email Template Sheet** — edit B2 (subject) and B3 (body)
5. Click **👨‍🏫 Create / View Class Teacher List** — fill in your class teachers
6. Authorize when prompted (first time only)

### 5. First-Time Authorization
1. Click any menu item → "Authorization required" → **Continue**
2. Choose your account
3. "Google hasn't verified this app" → **Advanced** → **Go to (project) (unsafe)**
4. **Allow**

---

## Class Teacher List (Auto-Fill)

The **"class teacher list"** sheet lets the script automatically fill in teacher initials during Step 1, so you don't have to type them manually every time.

### How to Set Up
1. Click **⚠️ Absence Automation → 👨‍🏫 Create / View Class Teacher List**
2. Replace the example data with your actual classes:

| 班別 (Class) | 教師縮寫 (Initials) |
|---|---|
| 1A | abc |
| 2A | lsk/ mky |
| 2B | cts/ tcy |
| 3A | lhyu/ lhl |

### Rules
- **Class names must match exactly** what appears in your data sheet (case-sensitive, spaces matter)
- Use **`/`** to separate two class teachers — e.g., `lsk/ mky`
- Both teachers will receive the same email
- If a class is NOT in the list, that row's initials are left blank (highlighted yellow) for you to fill manually
- You only need to set this up once — update it when teachers change

---

## Daily Workflow

### 1. Highlight absent students
- In your data sheet, color Column N **yellow** for each absent student

### 2. Step 1: Scan & Log
- Click **⚠️ Absence Automation** → **Step 1 ▶ Scan & Log Absences**
- Confirm → the script:
  - Writes records to the **"need follow up"** sheet
  - **Auto-fills teacher initials** from the class teacher list
  - Turns yellow cells **green** (processed)
- The summary tells you how many were auto-filled and which classes were missing

### 3. Review initials (if needed)
- Go to the **"need follow up"** sheet (it opens automatically)
- Column F (**教師縮寫**) should already be filled in
- Blank cells (highlighted light yellow) need manual input
- You can edit any initials before proceeding

### 4. Step 2: Prepare & Review
- Click **⚠️ Absence Automation** → **Step 2 📋 Prepare & Review Emails**
- The script groups students by class, builds one email per class teacher
- Opens the **"email preview"** sheet — check that:
  - ✅ Teacher emails are correct (Column C)
  - ✅ Subject and body look right
- You can **edit emails directly** in the preview sheet if needed
- Column G (系統用 — 勿改) contains internal row references — **do not edit**

### 5. Step 3: Send
- Click **⚠️ Absence Automation** → **Step 3 ✉ Send Prepared Emails**
- A dialog lists all recipients — final confirmation
- Click **Yes** → emails are sent
- Status updates to **"SENT ✅"** in preview and **"EMAILED ✅"** in follow-up

---

## Email Template

Edit on the **"email template"** sheet (no code changes needed):

| Cell | Content |
|------|---------|
| **B2** | Email subject line |
| **B3** | Email body |

### Placeholders (replaced automatically)

| Placeholder | Replaced With |
|---|---|
| `{{CLASS}}` | Class name (e.g., "2A") |
| `{{STUDENT_TABLE}}` | Formatted student table |
| `{{COUNT}}` | Number of students |
| `{{TODAY}}` | Today's date (YYYY-MM-DD) |

---

## Duplicate Prevention

| Color | Meaning |
|---|---|
| **Yellow** | Needs processing — picked up by Step 1 |
| **Green** | Already logged — Step 1 skips these |

In the "need follow up" sheet:

| Status | Meaning |
|---|---|
| **PENDING** | Logged, waiting for email |
| **EMAILED ✅** | Email sent — Step 2/3 skip these |

---

## Sheet Reference

### Data Sheet (auto-detected from `POSSIBLE_DATA_SHEETS`)
| Column | Data |
|---|---|
| A–E | Student fields (date, class, ID, name, subject) |
| N | Yellow/green highlight flag |

### "class teacher list" Sheet
| Col | Header | Notes |
|---|---|---|
| A | 班別 (Class) | Must match data sheet exactly |
| B | 教師縮寫 (Initials) | Use `/` for two teachers (e.g., `lsk/ mky`) |

### "need follow up" Sheet
| Col | Header | Notes |
|---|---|---|
| A | 缺考日期 | |
| B | 班別 | |
| C | 學號 | |
| D | 姓名（中） | |
| E | 缺考科目 | |
| **F** | **教師縮寫 (Initials)** | **Auto-filled from class teacher list; edit if needed** |
| G | 狀態 (Status) | PENDING → EMAILED ✅ |
| H | 處理時間 | Auto-filled timestamp |

### "email preview" Sheet
| Col | Header | Notes |
|---|---|---|
| A | 班別 | |
| B | 教師縮寫 | |
| C | 教師電郵 | Editable — you can correct before sending |
| D | 主旨 | |
| E | 內容 | |
| F | 狀態 | PENDING → SENT ✅ |
| G | (系統用 — 勿改) | Internal row references — **do not edit** |

### "email template" Sheet
| Col | Header | Notes |
|---|---|---|
| B2 | Subject | Use placeholders like `{{CLASS}}` |
| B3 | Body | Use placeholders; line breaks with `\n` or Alt+Enter |

---

## Menu Reference

| Menu Item | Function |
|---|---|
| Step 1 ▶ Scan & Log Absences | Scan yellow → log → auto-fill initials → mark green |
| Step 2 📋 Prepare & Review Emails | Build email preview from follow-up data |
| Step 3 ✉ Send Prepared Emails | Send all pending emails in preview |
| 📝 Create / Reset Email Template Sheet | Create or reset the email template |
| 👨‍🏫 Create / View Class Teacher List | Create or open the class teacher list |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| Menu doesn't appear | Refresh (F5), wait 5-10 seconds |
| "Cannot find sheet" / prompt appears | Your data sheet name isn't in `POSSIBLE_DATA_SHEETS` — add it to the list |
| Yellow rows not detected | Check `YELLOW_COLOR` hex code matches your actual yellow |
| Wrong student names or subjects | Check `COL_NAME` and `COL_SUBJECT` column numbers in settings |
| "Missing Email Template" | Click 📝 Create / Reset Email Template Sheet |
| Initials not auto-filled | Create the "class teacher list" sheet; ensure class names match exactly |
| "No PENDING rows" in Step 2 | Fill in initials in column F, or run Step 1 first |
| "No PENDING emails" in Step 3 | Run Step 2 first |
| Email not received | Check spam; verify initials are correct |
| "Exceeded email quota" | Google limit: ~100/day (free), ~1500/day (Workspace) |
| `Cannot call getUi()` error | Don't run `onOpen` from the ▶ button — it only works when opening the spreadsheet |
