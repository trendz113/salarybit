import os
import hmac
import hashlib
import tempfile
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import razorpay
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import fitz
from PIL import Image
import ctypes
import ctypes.util

try:
    ctypes.CDLL('libzbar.so.0')
except:
    try:
        ctypes.CDLL('/root/.nix-profile/lib/libzbar.so.0')
    except:
        pass

from pyzbar.pyzbar import decode
import io

app = Flask(__name__, static_folder="static")
CORS(app)

rzp = razorpay.Client(
    auth=(os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET"))
)

# ── SERVE HTML PAGES ──────────────────────────────────────
@app.route("/vahanclear.html")
def vahanclear_page():
    return send_from_directory("static", "vahanclear.html")

@app.route("/qr-decoder.html")
def qr_decoder_page():
    return send_from_directory(".", "qr-decoder.html")

# ── CREATE ORDER (SalaryBit QR) ───────────────────────────
@app.route("/api/create-order", methods=["POST", "OPTIONS"])
def create_order():
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": 4900,
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

# ── VERIFY PAYMENT + DECODE QR ────────────────────────────
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

    body     = f"{order_id}|{payment_id}"
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

    return jsonify({"success": True, "qr_strings": results, "count": len(results)})

# ── QR DECODE LOGIC ───────────────────────────────────────
def decode_qr_from_pdf(pdf_path):
    MAX_PIXELS = 500 * 500
    MIN_SIZE   = 50
    MAX_SCALED = 1200

    doc     = fitz.open(pdf_path)
    results = []
    seen    = set()

    for page_num in range(doc.page_count):
        page     = doc[page_num]
        img_list = page.get_images(full=True)

        for img_info in img_list:
            xref     = img_info[0]
            base_img = doc.extract_image(xref)
            iw       = base_img["width"]
            ih       = base_img["height"]

            if iw * ih > MAX_PIXELS or iw < MIN_SIZE or ih < MIN_SIZE:
                continue

            try:
                img     = Image.open(io.BytesIO(base_img["image"]))
                decoded = None

                found = decode(img)
                if found:
                    decoded = found[0].data.decode("utf-8", errors="replace")
                else:
                    for scale in [4, 8, 12]:
                        new_w  = min(iw * scale, MAX_SCALED)
                        new_h  = min(ih * scale, MAX_SCALED)
                        scaled = img.resize((new_w, new_h), Image.NEAREST)
                        found  = decode(scaled)
                        del scaled
                        if found:
                            decoded = found[0].data.decode("utf-8", errors="replace")
                            break
                del img

                if decoded and "+++" in decoded and decoded not in seen:
                    seen.add(decoded)
                    parts = decoded.split("+++", 1)
                    results.append({
                        "value":      decoded,
                        "doc_number": parts[0],
                        "page":       page_num + 1,
                        "label":      f"Page {page_num + 1}"
                    })
            except Exception as e:
                print(f"Image decode error: {e}")
                continue

    doc.close()
    return results

# ════════════════════════════════════════════════════════
#  VAHANCLEAR ROUTES
# ════════════════════════════════════════════════════════
SUREPASS_TOKEN = os.environ.get("SUREPASS_TOKEN", "")
vc_orders      = {}

def vc_fetch_vehicle(reg_no):
    res = requests.post(
        "https://sandbox.surepass.app/api/v1/rc/rc-full",
        json={"id_number": reg_no},
        headers={
            "Authorization": f"Bearer {SUREPASS_TOKEN}",
            "Content-Type": "application/json"
        },
        timeout=10
    )
    res.raise_for_status()
    return res.json().get("data", res.json())

def vc_build_preview(data):
    def mask(name):
        if not name or name == "—": return "••••••"
        parts = str(name).split()
        return parts[0][0] + "•••• " + (parts[1][0] + "••••" if len(parts) > 1 else "")
    return {
        "regNo":        data.get("rc_number") or data.get("reg_no", "—"),
        "vehicleClass": data.get("vehicle_class", "—"),
        "make":         data.get("maker_description") or data.get("maker_desc", "—"),
        "ownerName":    mask(data.get("owner_name", "")),
        "hasHypo":      bool(data.get("financer") or data.get("hypothecation_details")),
        "challanCount": data.get("challan_count", "?"),
    }

def vc_send_report_email(to_email, reg_no, data):
    has_hypo = bool(data.get("financer") or data.get("hypothecation_details"))
    owner    = data.get("owner_name", "—")
    make     = data.get("maker_description") or data.get("maker_desc", "—")
    model    = data.get("model", "—")
    financer = data.get("financer", "—")
    ins_upto = data.get("insurance_upto", "—")
    puc_upto = data.get("pucc_upto", "—")
    reg_date = data.get("registration_date") or data.get("reg_date", "—")
    challans = data.get("challan_count", "Check echallan.parivahan.gov.in")
    fuel     = data.get("fuel_type", "—")

    hypo_block = f"""
    <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:16px;margin:16px 0;">
      <b style="color:#856404;">⚠ Hypothecation Active — Financer: {financer}</b><br>
      <span style="font-size:13px;color:#856404;">Remove the loan lien before selling your vehicle.</span>
    </div>
    <h3 style="margin:16px 0 8px;">How to Remove Hypothecation</h3>
    <ol style="color:#444;line-height:2.2;padding-left:20px;">
      <li>Get the NOC letter from your bank.</li>
      <li>Visit parivahan.gov.in → Vehicle Services → Hypothecation Termination.</li>
      <li>Upload NOC and pay RTO fee (₹100–₹300).</li>
      <li>Updated RC delivered in 7–21 working days.</li>
    </ol>
    <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;padding:16px;margin:16px 0;
                font-family:monospace;font-size:13px;white-space:pre-wrap;">To: [Your Bank NOC Email]
Subject: Request for NOC — Vehicle {reg_no}

Dear Sir/Madam,
I, {owner}, request the NOC for hypothecation termination
of vehicle {reg_no} ({make} {model}). Loan is fully repaid.
Please issue NOC so I can update RC at RTO.

Regards, {owner}</div>""" if has_hypo else """
    <div style="background:#d1e7dd;border:1px solid #0f5132;border-radius:8px;padding:16px;margin:16px 0;">
      <b style="color:#0f5132;">✓ No Hypothecation — RC is clear. Safe to sell.</b>
    </div>"""

    html = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;padding:24px;">
  <div style="background:#12100e;color:#c8860a;padding:18px 24px;border-radius:8px 8px 0 0;">
    <b style="font-size:20px;">🚗 VahanClear</b>
    <div style="font-size:13px;opacity:.7;">Full RC Report — {reg_no}</div>
  </div>
  <table style="width:100%;border-collapse:collapse;margin:16px 0;">
    <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;width:40%;">Registration No</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{reg_no}</td></tr>
    <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Owner Name</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{owner}</td></tr>
    <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Make & Model</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{make} {model}</td></tr>
    <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Fuel Type</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{fuel}</td></tr>
    <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Registration Date</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{reg_date}</td></tr>
    <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Insurance Valid Upto</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{ins_upto}</td></tr>
    <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">PUC Valid Upto</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{puc_upto}</td></tr>
    <tr><td style="padding:8px 12px;border:1px solid #dee2e6;background:#f8f9fa;font-weight:600;">Pending Challans</td><td style="padding:8px 12px;border:1px solid #dee2e6;">{challans}</td></tr>
  </table>
  {hypo_block}
  <p style="font-size:12px;color:#999;text-align:center;margin-top:24px;">VahanClear · salarybit.in · Data from VAHAN via SurePass</p>
</body></html>"""

    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Your Vehicle RC Report — {reg_no}"
    msg["From"]    = f"VahanClear <{gmail_user}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))

    # Port 587 + STARTTLS (Railway blocks port 465)
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(gmail_user, gmail_pass)
        smtp.sendmail(gmail_user, to_email, msg.as_string())

@app.route("/api/vc/preview", methods=["POST", "OPTIONS"])
def vc_preview():
    if request.method == "OPTIONS": return "", 200
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
        return jsonify({"ok": False, "error": "Could not fetch vehicle data."}), 502

@app.route("/api/vc/create-order", methods=["POST", "OPTIONS"])
def vc_create_order():
    if request.method == "OPTIONS": return "", 200
    body   = request.get_json()
    reg_no = (body or {}).get("vehicleNumber", "").strip().upper()
    email  = (body or {}).get("email", "").strip()
    phone  = (body or {}).get("phone", "").strip()
    if not reg_no or not email:
        return jsonify({"ok": False, "error": "Missing fields"}), 400
    try:
        data  = vc_fetch_vehicle(reg_no)
        order = rzp.order.create({
            "amount": 8000, "currency": "INR",
            "receipt": f"vc_{os.urandom(4).hex()}",
            "notes": {"vehicleNumber": reg_no, "email": email},
        })
        vc_orders[order["id"]] = {
            "vehicleData": data, "vehicleNumber": reg_no,
            "email": email, "phone": phone, "paid": False,
        }
        return jsonify({"ok": True, "orderId": order["id"], "amount": order["amount"]})
    except Exception as e:
        print(f"vc_create_order error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/vc/verify-payment", methods=["POST", "OPTIONS"])
def vc_verify_payment():
    if request.method == "OPTIONS": return "", 200
    body       = request.get_json()
    order_id   = (body or {}).get("razorpay_order_id", "")
    payment_id = (body or {}).get("razorpay_payment_id", "")
    signature  = (body or {}).get("razorpay_signature", "")
    expected   = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    if expected != signature:
        return jsonify({"ok": False, "error": "Payment verification failed"}), 400
    # Fetch order details directly from Razorpay — no memory needed
    try:
        order  = rzp.order.fetch(order_id)
        reg_no = order.get("notes", {}).get("vehicleNumber", "")
        email  = order.get("notes", {}).get("email", "")
    except Exception as e:
        print(f"vc_fetch_order error: {e}")
        return jsonify({"ok": False, "error": "Could not fetch order details"}), 500

    if not reg_no or not email:
        return jsonify({"ok": False, "error": "Missing vehicle or email in order"}), 400

    try:
        data = vc_fetch_vehicle(reg_no)
    except Exception as e:
        print(f"vc_fetch_vehicle error: {e}")
        return jsonify({"ok": False, "error": "Could not fetch vehicle data"}), 502

    try:
        vc_send_report_email(email, reg_no, data)
        return jsonify({"ok": True, "message": "Report sent to your email"})
    except Exception as e:
        print(f"vc_email error: {e}")
        return jsonify({"ok": False, "error": f"Payment done but email failed: {str(e)}"}), 500

# ── HEALTH CHECK ──────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "SalaryBit + VahanClear"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
