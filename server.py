import os
import hmac
import hashlib
import json
import tempfile
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import razorpay
from flask import Flask, request, jsonify
from flask_cors import CORS
import fitz  # PyMuPDF
from PIL import Image
import ctypes
import ctypes.util

# Help pyzbar find zbar on Railway/nix
try:
    ctypes.CDLL('libzbar.so.0')
except:
    try:
        ctypes.CDLL('/root/.nix-profile/lib/libzbar.so.0')
    except:
        pass
from pyzbar.pyzbar import decode
import io

app = Flask(__name__)
CORS(app)  # Allow all origins

# Razorpay client
rzp = razorpay.Client(
    auth=(os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET"))
)


# ════════════════════════════════════════════════════════════
#  SALARYBIT — existing routes (unchanged)
# ════════════════════════════════════════════════════════════

# ── CREATE ORDER (SalaryBit ₹49) ─────────────────────────
@app.route("/api/create-order", methods=["POST", "OPTIONS"])
def create_order():
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": 4900,        # ₹49 in paise — hardcoded
            "currency": "INR",
            "receipt": f"qr_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
        })
    except Exception as e:
        print(f"create-order error: {e}")
        return jsonify({"error": str(e)}), 500


# ── VERIFY PAYMENT + DECODE QR ───────────────────────────
@app.route("/api/verify-and-decode", methods=["POST", "OPTIONS"])
def verify_and_decode():
    if request.method == "OPTIONS":
        return "", 200

    order_id   = request.form.get("razorpay_order_id")
    payment_id = request.form.get("razorpay_payment_id")
    signature  = request.form.get("razorpay_signature")
    pdf_file   = request.files.get("pdf")

    if not all([order_id, payment_id, signature, pdf_file]):
        return jsonify({"success": False, "error": "Missing required fields."}), 400

    body = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()

    if expected != signature:
        return jsonify({"success": False, "error": "Payment verification failed."}), 400

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = tmp.name
        pdf_file.save(pdf_path)

    try:
        results = decode_qr_from_pdf(pdf_path)
    finally:
        try:
            os.unlink(pdf_path)
        except:
            pass

    if not results:
        return jsonify({
            "success": False,
            "error": "No QR code found in this PDF. A refund will be processed within 24 hours."
        })

    return jsonify({
        "success": True,
        "qr_strings": results,
        "count": len(results)
    })


# ── QR DECODE LOGIC ───────────────────────────────────────
def decode_qr_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    results = []
    seen = set()

    for page_num in range(doc.page_count):
        page = doc[page_num]
        img_list = page.get_images(full=True)

        for img_info in img_list:
            xref = img_info[0]
            try:
                base_img = doc.extract_image(xref)
                img = Image.open(io.BytesIO(base_img["image"]))

                decoded = None
                for scale in [1, 4, 8, 12]:
                    w = img.width * scale
                    h = img.height * scale
                    scaled = img.resize((w, h), Image.NEAREST)
                    found = decode(scaled)
                    if found:
                        decoded = found[0].data.decode("utf-8", errors="replace")
                        break

                if decoded and "+++" in decoded and decoded not in seen:
                    seen.add(decoded)
                    parts = decoded.split("+++", 1)
                    results.append({
                        "value": decoded,
                        "doc_number": parts[0],
                        "page": page_num + 1,
                        "label": f"Page {page_num + 1}"
                    })

            except Exception as e:
                print(f"Image decode error page {page_num + 1}: {e}")
                continue

    doc.close()
    return results


# ── HEALTH CHECK ─────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "SalaryBit + VahanClear"})


# ════════════════════════════════════════════════════════════
#  VAHANCLEAR — new routes
# ════════════════════════════════════════════════════════════

# In-memory order store (vehicle data saved until payment verified)
vc_orders = {}


def vc_fetch_vehicle(reg_no):
    """Call Surepass RC Full API."""
    res = requests.post(
        "https://sandbox.surepass.app/api/v1/rc/rc-full",
        # ↑ Change to production when ready:
        # "https://kyc-api.surepass.app/api/v1/rc/rc-full"
        json={"id_number": reg_no},
        headers={"Authorization": f"Bearer {os.environ.get('SUREPASS_TOKEN', '')}"},
        timeout=10
    )
    res.raise_for_status()
    return res.json().get("data", {})


def vc_build_preview(data):
    """Return blurred/safe fields for free preview."""
    def mask(name):
        if not name or name == "—":
            return "••••••"
        parts = name.split()
        return parts[0][0] + "•••• " + (parts[1][0] + "••••" if len(parts) > 1 else "")

    has_hypo = bool(data.get("hypothecation_details"))
    return {
        "regNo":        data.get("registration_number", "—"),
        "vehicleClass": data.get("vehicle_category", "—"),
        "make":         data.get("maker_description", "—"),
        "ownerName":    mask(data.get("owner_name", "")),
        "hasHypo":      has_hypo,
        "challanCount": data.get("challan_count", "?"),
    }


def vc_send_report_email(to_email, reg_no, data):
    """Build full report and send via Gmail SMTP."""
    has_hypo = bool(data.get("hypothecation_details"))
    owner    = data.get("owner_name", "—")
    make     = data.get("maker_description", "—")
    model    = data.get("model", "—")
    financer = (data.get("hypothecation_details") or {}).get("financier_name", "—") if has_hypo else "—"
    ins_upto = data.get("insurance_upto", "—")
    puc_upto = data.get("pucc_upto", "—")
    reg_date = data.get("registration_date", "—")
    challans = data.get("challan_count", "Check echallan.parivahan.gov.in")
    fuel     = data.get("fuel_description", "—")
    category = data.get("vehicle_category", "—")

    hypo_block = f"""
    <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:16px;margin:16px 0;">
      <b style="color:#856404;">⚠ Hypothecation Active — Financer: {financer}</b><br>
      <span style="font-size:13px;color:#856404;">
        Your RC shows an active loan lien. You must remove this before selling the vehicle.
      </span>
    </div>""" if has_hypo else """
    <div style="background:#d1e7dd;border:1px solid #0f5132;border-radius:8px;padding:16px;margin:16px 0;">
      <b style="color:#0f5132;">✓ No Hypothecation — RC is clear.</b>
    </div>"""

    bank_draft = f"""
    <h2 style="font-size:17px;color:#1a1a2e;margin:24px 0 8px;">Bank Email Draft — Request Your NOC</h2>
    <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;padding:16px;
                font-family:monospace;font-size:13px;line-height:1.9;white-space:pre-wrap;">To: [Your Bank NOC / Loan Closure Email]
Subject: Request for NOC — Vehicle {reg_no}

Dear Sir/Madam,

I, {owner}, request the No Objection Certificate (NOC)
for hypothecation termination of my vehicle.

Vehicle Registration No : {reg_no}
Make & Model            : {make} {model}
Registered Owner        : {owner}

My vehicle loan is fully repaid. Please issue the NOC /
Hypothecation Termination Letter at the earliest so I
can update the RC at the RTO.

Kindly email the NOC and also post the physical copy
to my registered address.

Thanking you,
{owner}
[Your Loan Account Number]
[Your Registered Mobile Number]</div>
    <p style="font-size:12px;color:#666;margin-top:8px;">
      📌 Find your bank's NOC email — search "[Bank Name] NOC email vehicle hypothecation"
      or call their customer care. E.g. HDFC: noc.vehicle@hdfcbank.com
    </p>""" if has_hypo else ""

    steps = """
    <h2 style="font-size:17px;color:#1a1a2e;margin:24px 0 8px;">How to Remove Hypothecation Online</h2>
    <ol style="color:#444;line-height:2.2;padding-left:20px;">
      <li>Collect the <b>NOC letter</b> from your bank (branch or NetBanking portal).</li>
      <li>Visit <a href="https://parivahan.gov.in/vahanservice" style="color:#0d6efd;">
          parivahan.gov.in/vahanservice</a> → <b>Vehicle Services → Hypothecation Termination</b>.</li>
      <li>Login with your <b>registered mobile number</b> (same as RC).</li>
      <li>Enter your vehicle number and upload the bank NOC (PDF/JPG, max 2MB).</li>
      <li>Pay the RTO fee online — ₹100 to ₹300 depending on your state.</li>
      <li>Submit — save the <b>acknowledgement number</b> you receive.</li>
      <li>Updated Smart Card RC delivered by post in <b>7–21 working days</b>.</li>
    </ol>
    <p style="font-size:13px;background:#eef6ff;border-radius:7px;padding:12px;margin-top:8px;color:#444;">
      💡 <b>Tip:</b> If your RC address differs from your current address, file
      <b>Form 33</b> (address change) at the same time — saves a separate RTO visit.
    </p>""" if has_hypo else ""

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/></head>
<body style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;padding:24px;color:#222;">
  <div style="background:#12100e;color:#c8860a;padding:18px 24px;border-radius:8px 8px 0 0;">
    <div style="font-size:22px;font-weight:700;">🚗 VahanClear</div>
    <div style="font-size:13px;opacity:.7;margin-top:4px;">Vehicle RC Report — {reg_no}</div>
  </div>
  <div style="padding:20px 0;">
    <h2 style="font-size:17px;color:#1a1a2e;margin:0 0 12px;">Vehicle Details</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:8px;">
      <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;width:40%;">Registration No</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{reg_no}</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Owner Name</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{owner}</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Make & Model</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{make} {model}</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Vehicle Category</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{category}</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Fuel Type</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{fuel}</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Registration Date</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{reg_date}</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Insurance Valid Upto</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{ins_upto}</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">PUC Valid Upto</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{puc_upto}</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Pending Challans</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{challans}</td></tr>
    </table>
    {hypo_block}
    {bank_draft}
    {steps}
    <hr style="margin:24px 0;border:none;border-top:1px solid #eee;"/>
    <p style="font-size:12px;color:#999;text-align:center;">
      VahanClear · vahanclear.in · Data sourced from VAHAN via Surepass<br>
      Questions? Reply to this email.
    </p>
  </div>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Your Vehicle Report — {reg_no}"
    msg["From"]    = f"VahanClear <{os.environ.get('GMAIL_USER', '')}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(
            os.environ.get("GMAIL_USER", ""),
            os.environ.get("GMAIL_APP_PASSWORD", "")
        )
        smtp.sendmail(os.environ.get("GMAIL_USER", ""), to_email, msg.as_string())


# ── VC: FREE PREVIEW ─────────────────────────────────────
@app.route("/api/vc/preview", methods=["POST", "OPTIONS"])
def vc_preview():
    if request.method == "OPTIONS":
        return "", 200
    body   = request.get_json()
    reg_no = (body or {}).get("vehicleNumber", "").strip().upper()
    if not reg_no:
        return jsonify({"ok": False, "error": "Vehicle number required"}), 400
    try:
        data    = vc_fetch_vehicle(reg_no)
        preview = vc_build_preview(data)
        return jsonify({"ok": True, "preview": preview})
    except Exception as e:
        print(f"vc_preview error: {e}")
        return jsonify({"ok": False, "error": "Could not fetch vehicle data. Check the number."}), 502


# ── VC: CREATE ORDER (₹80) ───────────────────────────────
@app.route("/api/vc/create-order", methods=["POST", "OPTIONS"])
def vc_create_order():
    if request.method == "OPTIONS":
        return "", 200
    body   = request.get_json()
    reg_no = (body or {}).get("vehicleNumber", "").strip().upper()
    email  = (body or {}).get("email", "").strip()
    phone  = (body or {}).get("phone", "").strip()
    if not reg_no or not email:
        return jsonify({"ok": False, "error": "Missing fields"}), 400
    try:
        data  = vc_fetch_vehicle(reg_no)
        order = rzp.order.create({
            "amount":   8000,   # ₹80 in paise
            "currency": "INR",
            "receipt":  f"vc_{os.urandom(4).hex()}",
            "notes":    {"vehicleNumber": reg_no, "email": email},
        })
        vc_orders[order["id"]] = {
            "vehicleData":   data,
            "vehicleNumber": reg_no,
            "email":         email,
            "phone":         phone,
            "paid":          False,
        }
        return jsonify({"ok": True, "orderId": order["id"], "amount": order["amount"]})
    except Exception as e:
        print(f"vc_create_order error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ── VC: VERIFY PAYMENT + EMAIL REPORT ────────────────────
@app.route("/api/vc/verify-payment", methods=["POST", "OPTIONS"])
def vc_verify_payment():
    if request.method == "OPTIONS":
        return "", 200
    body       = request.get_json()
    order_id   = (body or {}).get("razorpay_order_id", "")
    payment_id = (body or {}).get("razorpay_payment_id", "")
    signature  = (body or {}).get("razorpay_signature", "")
    email      = (body or {}).get("email", "")
    phone      = (body or {}).get("phone", "")
    vehicle_no = (body or {}).get("vehicleNumber", "")

    # Verify signature
    msg      = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()
    if expected != signature:
        return jsonify({"ok": False, "error": "Payment verification failed"}), 400

    # Try in-memory first, fallback to re-fetching vehicle data
    record = vc_orders.get(order_id)
    if record:
        email      = record["email"]
        phone      = record["phone"]
        vehicle_no = record["vehicleNumber"]
        data       = record["vehicleData"]
    else:
        # Server restarted — re-fetch vehicle data using order notes
        try:
            order      = rzp.order.fetch(order_id)
            notes      = order.get("notes", {})
            vehicle_no = notes.get("vehicleNumber", vehicle_no)
            email      = notes.get("email", email)
            data       = vc_fetch_vehicle(vehicle_no)
        except Exception as e:
            print(f"vc re-fetch error: {e}")
            return jsonify({"ok": False, "error": "Order not found. Contact support with payment ID."}), 404

    try:
        vc_send_report_email(email, vehicle_no, data)
        return jsonify({"ok": True, "message": "Report sent to your email"})
    except Exception as e:
        print(f"vc_email error: {e}")
        return jsonify({"ok": False, "error": "Payment done but email failed. Contact support."}), 500


# ════════════════════════════════════════════════════════════
#  START
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
