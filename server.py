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
CORS(app)  # Allow all origins

# Razorpay client
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

    # Step 1: Get form fields
    order_id   = request.form.get("razorpay_order_id")
    payment_id = request.form.get("razorpay_payment_id")
    signature  = request.form.get("razorpay_signature")
    pdf_file   = request.files.get("pdf")

    if not all([order_id, payment_id, signature, pdf_file]):
        return jsonify({"success": False, "error": "Missing required fields."}), 400

    # Step 2: Verify Razorpay signature
    body = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()

    if expected != signature:
        return jsonify({"success": False, "error": "Payment verification failed."}), 400

    # Step 3: Save PDF to temp file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = tmp.name
        pdf_file.save(pdf_path)

    # Step 4: Decode QR from PDF
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
    """
    Extract all QR codes from a PDF using PyMuPDF + pyzbar.
    Upscales images 4x for reliable decode of small QRs.
    """
    doc = fitz.open(pdf_path)
    results = []
    seen = set()
print(f"PDF pages: {doc.page_count}")
for page_num in range(doc.page_count):
    page = doc[page_num]
    img_list = page.get_images(full=True)
    print(f"Page {page_num+1}: {len(img_list)} images found")
    for page_num in range(doc.page_count):
        page = doc[page_num]
        img_list = page.get_images(full=True)

        for img_info in img_list:
            xref = img_info[0]
            try:
                base_img = doc.extract_image(xref)
                img = Image.open(io.BytesIO(base_img["image"]))

                decoded = None
                # Try upscaling 1x, 4x, 8x, 12x for small QR codes
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


# ── HEALTH CHECK ──────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "SalaryBit QR Decoder"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
