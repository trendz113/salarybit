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
import urllib.request
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


# ── CREATE RESUME ORDER (₹99) ────────────────────────────
@app.route("/api/create-resume-order", methods=["POST", "OPTIONS"])
def create_resume_order():
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": 9900,        # ₹99 in paise — hardcoded
            "currency": "INR",
            "receipt": f"resume_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id":     order["id"],
            "amount":       order["amount"],
            "currency":     order["currency"],
            "razorpay_key": os.environ.get("RAZORPAY_KEY_ID"),
        })
    except Exception as e:
        print(f"create-resume-order error: {e}")
        return jsonify({"error": str(e)}), 500


# ── AI RESUME REWRITER ────────────────────────────────────
@app.route("/api/rewrite-resume", methods=["POST", "OPTIONS"])
def rewrite_resume():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json()
    resume = data.get("resume", "").strip()
    jd = data.get("jd", "").strip()

    if not resume or not jd:
        return jsonify({"error": "Missing resume or jd"}), 400

    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        return jsonify({"error": "GROQ_API_KEY not set on server"}), 500

    prompt = f"""You are an expert ATS resume optimizer for the Indian job market.

RESUME:
{resume}

JOB DESCRIPTION:
{jd}

Analyze and respond ONLY with valid JSON, no markdown, no explanation:
{{
  "ats_before": <integer 0-100, realistic ATS match score of original resume>,
  "ats_after": <integer 0-100, ATS score after rewriting>,
  "present_keywords": [<array of important keywords from JD already in resume>],
  "missing_keywords": [<array of important keywords from JD missing in resume>],
  "rewritten_resume": "<full rewritten resume, ATS optimized, same facts, better phrasing, keywords added naturally>"
}}"""

    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.3,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {groq_key}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        raw = result["choices"][0]["message"]["content"]
        clean = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean)
        return jsonify(parsed)

    except Exception as e:
        print(f"rewrite-resume error: {e}")
        return jsonify({"error": str(e)}), 500



# ── FOOTBALL DATA PROXY ───────────────────────────────────
import requests as http_requests

@app.route('/api/football')
def football_proxy():
    endpoint = request.args.get('endpoint', '')
    if not endpoint:
        return jsonify({'error': 'No endpoint'}), 400
    r = http_requests.get(
        f'https://api.football-data.org/v4{endpoint}',
        headers={'X-Auth-Token': '2c749c3fe0504fd8859b82035a268f47'},
        timeout=10
    )
    return jsonify(r.json())

# ── HEALTH CHECK ──────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "SalaryBit QR Decoder"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
