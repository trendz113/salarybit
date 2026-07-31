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
 */

function doPost(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

    // Add header row once, if the sheet is empty
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(["Timestamp", "Email", "Source", "IP (if provided)"]);
    }

    var data = JSON.parse(e.postData.contents);
    var email = (data.email || "").toString().trim().toLowerCase();
    var source = (data.source || "unknown").toString().trim();

    if (!email || email.indexOf("@") === -1) {
      return ContentService.createTextOutput(
        JSON.stringify({ status: "error", message: "invalid email" })
      ).setMimeType(ContentService.MimeType.JSON);
    }

    sheet.appendRow([new Date(), email, source, ""]);

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
