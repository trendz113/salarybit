/**
 * SalaryBit Lead Capture Webhook
 * ---------------------------------
 * Receives POST requests from server_railway.py's /api/capture-lead
 * endpoint and appends each lead as a new row in this Sheet.
 *
 * SETUP:
 * 1. Create a new Google Sheet (or open an existing one you want to use).
 * 2. Extensions -> Apps Script. Delete any starter code, paste this whole file.
 * 3. Click the disk icon to save. Name the project "SalaryBit Leads".
 * 4. Click "Deploy" -> "New deployment".
 *    - Select type: "Web app"
 *    - Description: "Lead capture v1"
 *    - Execute as: "Me"
 *    - Who has access: "Anyone" (required so the Railway server can call it
 *      without a Google login — the URL itself is your secret, keep it private)
 * 5. Click "Deploy". Authorize the permissions it asks for (it's your own
 *    script writing to your own Sheet).
 * 6. Copy the "Web app URL" it gives you — looks like:
 *    https://script.google.com/macros/s/AKfycb.../exec
 * 7. Send me that URL (or set it as GOOGLE_SHEET_WEBHOOK_URL on Railway
 *    yourself — see instructions I gave you separately).
 *
 * Every time you push new code to this script, you must create a NEW
 * deployment (or "Manage deployments" -> edit -> new version) for changes
 * to take effect — editing the code alone does not update the live URL.
 *
 * UPGRADING AN EXISTING SHEET (you already have one live):
 * This version adds a 5th column, "PDF Sent" (column E), used by
 * sendPendingLeadEmails() below to track who's already been emailed.
 * If your sheet already has header row "Timestamp | Email | Source |
 * IP (if provided)" without a 5th column, just type "PDF Sent" into E1
 * yourself — the header-creation code below only runs on a brand new
 * empty sheet, it won't touch an existing header row.
 */

function doPost(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

    // Add header row once, if the sheet is empty
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(["Timestamp", "Email", "Source", "IP (if provided)", "PDF Sent"]);
    }

    var data = JSON.parse(e.postData.contents);
    var email = (data.email || "").toString().trim().toLowerCase();
    var source = (data.source || "unknown").toString().trim();

    if (!email || email.indexOf("@") === -1) {
      return ContentService.createTextOutput(
        JSON.stringify({ status: "error", message: "invalid email" })
      ).setMimeType(ContentService.MimeType.JSON);
    }

    sheet.appendRow([new Date(), email, source, "", ""]);

    return ContentService.createTextOutput(
      JSON.stringify({ status: "ok" })
    ).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(
      JSON.stringify({ status: "error", message: err.toString() })
    ).setMimeType(ContentService.MimeType.JSON);
  }
}

// Lets you sanity-check the deployment URL in a browser (GET request)
function doGet(e) {
  return ContentService.createTextOutput(
    JSON.stringify({ status: "ok", message: "SalaryBit lead webhook is live" })
  ).setMimeType(ContentService.MimeType.JSON);
}

/**
 * === Daily auto-send: Old vs New Tax Regime PDF ===
 *
 * Emails the CA-style tax regime PDF guide to anyone in this sheet whose
 * "PDF Sent" column (E) is still blank, then marks them as sent so they
 * never get a duplicate email.
 *
 * Run this once manually to test (Run > sendPendingLeadEmails, check the
 * Execution log). Then set it on a daily timer:
 *   Triggers (clock icon, left sidebar) > + Add Trigger
 *   - Function: sendPendingLeadEmails
 *   - Event source: Time-driven
 *   - Type: Day timer, pick any hour (e.g. 9am-10am)
 *   - Save (authorize if asked)
 *
 * The PDF is fetched fresh from the live site on every send, so if the
 * guide is ever updated on salarybit.in, this always sends the latest
 * version with no script changes needed.
 */
function sendPendingLeadEmails() {
  var PDF_URL = "https://salarybit.in/assets/pdf/salarybit-old-vs-new-tax-regime-guide.pdf";
  var SENDER_NAME = "SalaryBit";
  var SUBJECT = "Your Old vs New Tax Regime guide (FY 2026-27)";

  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return; // nothing but headers

  var range = sheet.getRange(2, 1, lastRow - 1, 5); // A:E
  var values = range.getValues();

  var pdfBlob = null; // fetch lazily, only if there's at least one email to send

  for (var i = 0; i < values.length; i++) {
    var row = values[i];
    var email = row[1];
    var sentFlag = row[4];

    if (!email || sentFlag) continue; // skip blank or already-sent rows

    if (!pdfBlob) {
      var resp = UrlFetchApp.fetch(PDF_URL, { muteHttpExceptions: true });
      if (resp.getResponseCode() !== 200) {
        Logger.log("Could not fetch PDF, aborting run: HTTP " + resp.getResponseCode());
        return;
      }
      pdfBlob = resp.getBlob().setName("SalaryBit - Old vs New Tax Regime Guide.pdf");
    }

    try {
      MailApp.sendEmail({
        to: email,
        subject: SUBJECT,
        name: SENDER_NAME,
        htmlBody:
          "<p>Hi,</p>" +
          "<p>Thanks for signing up on SalaryBit — here's the full CA-style " +
          "breakdown of the Old vs New Tax Regime, with a complete deduction " +
          "checklist and a worked example, as promised.</p>" +
          "<p>You can also run the live comparison anytime with your own numbers: " +
          "<a href='https://salarybit.in/tools/old-vs-new-tax-regime.html'>" +
          "salarybit.in/tools/old-vs-new-tax-regime.html</a></p>" +
          "<p>No further emails from this — this was a one-time send.</p>" +
          "<p>— SalaryBit</p>",
        attachments: [pdfBlob],
      });

      // Mark this row's "PDF Sent" column with today's date
      sheet.getRange(i + 2, 5).setValue(new Date());

    } catch (sendErr) {
      Logger.log("Failed to email " + email + ": " + sendErr.toString());
      // leave PDF Sent blank so it retries on the next run
    }
  }
}
