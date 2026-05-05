import os
import hmac
import hashlib
import json
import tempfile
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
CORS(app)

rzp = razorpay.Client(
    auth=(os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET"))
)

# ── CREATE ORDER ──────────────────────────────────────────
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
            "amount":   order["amount"],
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

    # Verify Razorpay signature
    body = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()

    if expected != signature:
        return jsonify({"success": False, "error": "Payment verification failed."}), 400

    # Save PDF to temp file
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
    # FIX 1: Skip images larger than 500x500 — those are property photos,
    # not QR codes. Loading + upscaling them causes the SIGKILL OOM crash.
    MAX_PIXELS  = 500 * 500   # anything bigger is not a QR code
    MIN_SIZE    = 50          # anything smaller can't be a QR code
    MAX_SCALED  = 1200        # cap upscaled dimension to stay in memory

    doc = fitz.open(pdf_path)
    results = []
    seen = set()

    # FIX 2: Removed duplicate loop and fixed indentation
    print(f"PDF opened: {doc.page_count} pages")

    for page_num in range(doc.page_count):
        page     = doc[page_num]
        img_list = page.get_images(full=True)
        print(f"Page {page_num + 1}: {len(img_list)} embedded images")

        for img_info in img_list:
            xref     = img_info[0]
            base_img = doc.extract_image(xref)
            iw       = base_img["width"]
            ih       = base_img["height"]

            print(f"  Image size: {iw}x{ih}")

            # FIX 1: Skip large images (property photos, backgrounds)
            if iw * ih > MAX_PIXELS:
                print(f"  → SKIPPED (too large, not a QR code)")
                continue

            # Skip tiny images that can't be QR codes
            if iw < MIN_SIZE or ih < MIN_SIZE:
                print(f"  → SKIPPED (too small)")
                continue

            try:
                img = Image.open(io.BytesIO(base_img["image"]))

                decoded = None

                # Try at original size first
                found = decode(img)
                if found:
                    decoded = found[0].data.decode("utf-8", errors="replace")
                else:
                    # Upscale small QR images — capped to MAX_SCALED
                    for scale in [4, 8, 12]:
                        new_w = min(iw * scale, MAX_SCALED)
                        new_h = min(ih * scale, MAX_SCALED)
                        scaled = img.resize((new_w, new_h), Image.NEAREST)
                        found  = decode(scaled)
                        del scaled  # free memory immediately
                        if found:
                            decoded = found[0].data.decode("utf-8", errors="replace")
                            break

                del img  # free memory immediately

                if decoded and "+++" in decoded and decoded not in seen:
                    seen.add(decoded)
                    parts = decoded.split("+++", 1)
                    results.append({
                        "value":      decoded,
                        "doc_number": parts[0],
                        "page":       page_num + 1,
                        "label":      f"Page {page_num + 1}"
                    })
                    print(f"  → DECODED: {decoded[:60]}...")

            except Exception as e:
                print(f"  Image decode error: {e}")
                continue

    doc.close()
    return results


# ── HEALTH CHECK ──────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "SalaryBit QR Decoder"})

# ════════════════════════════════════════════════════════════
#  VAHANCLEAR ROUTES  (SurePass RC lookup)
# ════════════════════════════════════════════════════════════
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SUREPASS_TOKEN = os.environ.get("SUREPASS_TOKEN", "")
GMAIL_USER     = os.environ.get("GMAIL_USER", "")
GMAIL_PASS     = os.environ.get("GMAIL_APP_PASSWORD", "")

vc_orders = {}  # orderId → {vehicleData, email, phone, paid}

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
      <span style="font-size:13px;color:#856404;">Your RC has an active loan lien. Remove it before selling.</span>
    </div>
    <h3 style="color:#1a1a2e;margin:20px 0 8px;">How to Remove Hypothecation</h3>
    <ol style="color:#444;line-height:2.2;padding-left:20px;">
      <li>Get the <b>NOC letter</b> from your bank (branch or NetBanking).</li>
      <li>Visit <a href="https://parivahan.gov.in/vahanservice">parivahan.gov.in/vahanservice</a> → Vehicle Services → Hypothecation Termination.</li>
      <li>Login with your registered mobile number, upload the NOC.</li>
      <li>Pay RTO fee online (₹100–₹300 depending on state).</li>
      <li>Updated RC delivered by post in 7–21 working days.</li>
    </ol>
    <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;padding:16px;margin:16px 0;font-family:monospace;font-size:13px;white-space:pre-wrap;">To: [Your Bank NOC Email]
Subject: Request for NOC — Vehicle {reg_no}

Dear Sir/Madam,
I, {owner}, request the NOC for hypothecation termination
of vehicle {reg_no} ({make} {model}). My loan is fully repaid.
Please issue the NOC so I can update the RC at RTO.

Regards,
{owner}
[Your Loan Account Number]</div>""" if has_hypo else """
    <div style="background:#d1e7dd;border:1px solid #0f5132;border-radius:8px;padding:16px;margin:16px 0;">
      <b style="color:#0f5132;">✓ No Hypothecation — RC is clear. You can sell freely.</b>
    </div>"""

    html = f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;padding:24px;color:#222;">
  <div style="background:#12100e;color:#c8860a;padding:18px 24px;border-radius:8px 8px 0 0;">
    <div style="font-size:22px;font-weight:700;">🚗 VahanClear</div>
    <div style="font-size:13px;opacity:.7;margin-top:4px;">Full RC Report — {reg_no}</div>
  </div>
  <div style="padding:20px 0;">
    <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
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
    <hr style="margin:24px 0;border:none;border-top:1px solid #eee;"/>
    <p style="font-size:12px;color:#999;text-align:center;">VahanClear · salarybit.in · Data from VAHAN via SurePass</p>
  </div>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Your Vehicle RC Report — {reg_no}"
    msg["From"]    = f"VahanClear <{GMAIL_USER}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_PASS)
        smtp.sendmail(GMAIL_USER, to_email, msg.as_string())

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
        return jsonify({"ok": False, "error": "Could not fetch vehicle data. Check the number."}), 502

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
    record = vc_orders.get(order_id)
    if not record: return jsonify({"ok": False, "error": "Order not found"}), 404
    if record["paid"]: return jsonify({"ok": True, "alreadySent": True})
    record["paid"] = True
    try:
        vc_send_report_email(record["email"], record["vehicleNumber"], record["vehicleData"])
        return jsonify({"ok": True, "message": "Report sent to your email"})
    except Exception as e:
        print(f"vc_email error: {e}")
        return jsonify({"ok": False, "error": "Payment done but email failed. Contact support."}), 500
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
