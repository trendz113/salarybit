/**
 * SalaryBit — e-Khata Tax Assistant Submission Webhook
 * -----------------------------------------------------
 * Receives POST requests from server_railway.py's /api/ekhata-submit
 * endpoint and appends each intake submission as a new row in this Sheet.
 * This is the durable copy — the local ekhata-submissions.jsonl fallback
 * on Railway is lost on every redeploy, so this Sheet is the real record.
 *
 * This is a SEPARATE Sheet/script from the existing lead-sheet-webhook.gs
 * — Ekhata submissions have a different shape (Owner Name, Documents,
 * Type, PID, etc.) from leads/feedback rows, so they don't belong in the
 * same sheet.
 *
 * SETUP:
 * 1. Create a NEW Google Sheet (don't reuse your leads sheet).
 * 2. Extensions -> Apps Script. Delete any starter code, paste this
 *    whole file.
 * 3. Click the disk icon to save. Name the project "e-Khata Submissions".
 * 4. Click "Deploy" -> "New deployment".
 *    - Select type: "Web app"
 *    - Description: "e-Khata submissions v1"
 *    - Execute as: "Me"
 *    - Who has access: "Anyone" (required so Railway can call it without
 *      a Google login — the URL itself is your secret, keep it private)
 * 5. Click "Deploy". Authorize the permissions it asks for.
 * 6. Copy the "Web app URL" — looks like:
 *    https://script.google.com/macros/s/AKfycb.../exec
 * 7. On Railway -> your project -> Variables, set:
 *    EKHATA_SHEET_WEBHOOK_URL = <that URL>
 *
 * Every time you edit this script's code, you must create a NEW
 * deployment (Manage deployments -> edit -> new version) for the
 * change to take effect on the live URL — saving alone isn't enough.
 *
 * Each row also gets the full submission as one JSON blob in the last
 * column ("Full Data (JSON)") — a safety net so nothing is ever lost
 * even if a future field isn't one of the named columns below yet.
 */

function doPost(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

    if (sheet.getLastRow() === 0) {
      sheet.appendRow([
        "Timestamp", "Owner Name", "Mobile", "Owner Email",
        "Documents", "Notes", "Full Data (JSON)"
      ]);
    }

    var data = JSON.parse(e.postData.contents);

    sheet.appendRow([
      new Date(),
      data["Owner Name"] || "",
      data["Mobile"] || "",
      data["Owner Email"] || "",
      data["Documents"] || "",
      data["Notes"] || "",
      JSON.stringify(data)
    ]);

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
    JSON.stringify({ status: "ok", message: "e-Khata submission webhook is live" })
  ).setMimeType(ContentService.MimeType.JSON);
}
