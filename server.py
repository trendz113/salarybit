import os
import hmac
import hashlib
import tempfile
import requests
import razorpay
from flask import Flask, request, jsonify
from flask_cors import CORS
import fitz
from PIL import Image
import ctypes

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

vc_orders = {}


# ════════════════════════════════════════════════════════════
#  SALARYBIT — unchanged
# ════════════════════════════════════════════════════════════

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
        return jsonify({"order_id": order["id"], "amount": order["amount"], "currency": order["currency"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    expected = hmac.new(os.environ.get("RAZORPAY_KEY_SECRET","").encode(), body.encode(), hashlib.sha256).hexdigest()
    if expected != signature:
        return jsonify({"success": False, "error": "Payment verification failed."}), 400
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = tmp.name
        pdf_file.save(pdf_path)
    try:
        results = decode_qr_from_pdf(pdf_path)
    finally:
        try: os.unlink(pdf_path)
        except: pass
    if not results:
        return jsonify({"success": False, "error": "No QR code found. Refund in 24 hours."})
    return jsonify({"success": True, "qr_strings": results, "count": len(results)})


def decode_qr_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    results = []
    seen = set()
    for page_num in range(doc.page_count):
        page = doc[page_num]
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_img = doc.extract_image(xref)
                img = Image.open(io.BytesIO(base_img["image"]))
                decoded = None
                for scale in [1, 4, 8, 12]:
                    found = decode(img.resize((img.width*scale, img.height*scale), Image.NEAREST))
                    if found:
                        decoded = found[0].data.decode("utf-8", errors="replace")
                        break
                if decoded and "+++" in decoded and decoded not in seen:
                    seen.add(decoded)
                    parts = decoded.split("+++", 1)
                    results.append({"value": decoded, "doc_number": parts[0], "page": page_num+1, "label": f"Page {page_num+1}"})
            except Exception as e:
                print(f"QR decode error: {e}")
    doc.close()
    return results


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "SalaryBit + VahanClear"})


# ════════════════════════════════════════════════════════════
#  VAHANCLEAR
# ════════════════════════════════════════════════════════════

def clean(val, fallback="—"):
    """Return fallback if value is None, empty string, or the string 'null'."""
    if val is None or str(val).strip().lower() in ("", "null", "none", "n/a"):
        return fallback
    return str(val).strip()


def vc_fetch_vehicle(reg_no):
    res = requests.post(
        "https://sandbox.surepass.app/api/v1/rc/rc-full",
        # PRODUCTION → "https://kyc-api.surepass.app/api/v1/rc/rc-full"
        json={"id_number": reg_no},
        headers={"Authorization": f"Bearer {os.environ.get('SUREPASS_TOKEN', '')}"},
        timeout=10
    )
    res.raise_for_status()
    return res.json().get("data", {})


def vc_build_preview(data):
    def mask(name):
        n = clean(name, "")
        if not n:
            return "••••••"
        parts = n.split()
        return parts[0][0] + "•••• " + (parts[1][0] + "••••" if len(parts) > 1 else "")

    has_hypo = bool(data.get("hypothecation_details"))
    return {
        "regNo":        clean(data.get("registration_number")),
        "vehicleClass": clean(data.get("vehicle_category")),
        "make":         clean(data.get("maker_description")),
        "ownerName":    mask(data.get("owner_name", "")),
        "hasHypo":      has_hypo,
        "challanCount": clean(data.get("challan_count"), "0"),
    }


def vc_build_report(data, reg_no):
    has_hypo = bool(data.get("hypothecation_details"))
    hypo     = data.get("hypothecation_details") or {}

    # Build model string cleanly
    make  = clean(data.get("maker_description"))
    model = clean(data.get("model"), "")
    make_model = f"{make} {model}".strip() if model else make

    return {
        "regNo":             reg_no,
        "ownerName":         clean(data.get("owner_name")),
        "makeModel":         make_model,
        "vehicleCategory":   clean(data.get("vehicle_category")),
        "fuelType":          clean(data.get("fuel_description")),
        "regDate":           clean(data.get("registration_date")),
        "insuranceUpto":     clean(data.get("insurance_upto")),
        "pucUpto":           clean(data.get("pucc_upto")),
        "challanCount":      clean(data.get("challan_count"), "0"),
        "colour":            clean(data.get("colour")),
        "ownerCount":        clean(data.get("owner_count"), "1"),
        "hasHypo":           has_hypo,
        "financerName":      clean(hypo.get("financier_name")) if has_hypo else "None",
        "hypothecationDate": clean(hypo.get("hypothecation_date")) if has_hypo else "—",
    }


@app.route("/api/vc/preview", methods=["POST", "OPTIONS"])
def vc_preview():
    if request.method == "OPTIONS":
        return "", 200
    body   = request.get_json()
    reg_no = (body or {}).get("vehicleNumber", "").strip().upper()
    if not reg_no:
        return jsonify({"ok": False, "error": "Vehicle number required"}), 400
    try:
        data = vc_fetch_vehicle(reg_no)
        return jsonify({"ok": True, "preview": vc_build_preview(data)})
    except Exception as e:
        print(f"vc_preview error: {e}")
        return jsonify({"ok": False, "error": "Could not fetch vehicle data. Check the number."}), 502


@app.route("/api/vc/create-order", methods=["POST", "OPTIONS"])
def vc_create_order():
    if request.method == "OPTIONS":
        return "", 200
    body   = request.get_json()
    reg_no = (body or {}).get("vehicleNumber", "").strip().upper()
    if not reg_no:
        return jsonify({"ok": False, "error": "Missing vehicle number"}), 400
    try:
        data  = vc_fetch_vehicle(reg_no)
        order = rzp.order.create({
            "amount": 8000,
            "currency": "INR",
            "receipt": f"vc_{os.urandom(4).hex()}",
            "notes":  {"vehicleNumber": reg_no},
        })
        vc_orders[order["id"]] = {"vehicleData": data, "vehicleNumber": reg_no}
        return jsonify({"ok": True, "orderId": order["id"], "amount": order["amount"]})
    except Exception as e:
        print(f"vc_create_order error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/vc/verify-payment", methods=["POST", "OPTIONS"])
def vc_verify_payment():
    if request.method == "OPTIONS":
        return "", 200
    body       = request.get_json()
    order_id   = (body or {}).get("razorpay_order_id", "")
    payment_id = (body or {}).get("razorpay_payment_id", "")
    signature  = (body or {}).get("razorpay_signature", "")
    vehicle_no = (body or {}).get("vehicleNumber", "")

    msg      = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        msg.encode(), hashlib.sha256
    ).hexdigest()
    if expected != signature:
        return jsonify({"ok": False, "error": "Payment verification failed"}), 400

    record = vc_orders.get(order_id)
    if record:
        data       = record["vehicleData"]
        vehicle_no = record["vehicleNumber"]
    else:
        try:
            order      = rzp.order.fetch(order_id)
            vehicle_no = order.get("notes", {}).get("vehicleNumber", vehicle_no)
            data       = vc_fetch_vehicle(vehicle_no)
        except Exception as e:
            print(f"vc re-fetch error: {e}")
            return jsonify({"ok": False, "error": "Could not retrieve data. Contact support."}), 500

    report = vc_build_report(data, vehicle_no)
    return jsonify({"ok": True, "report": report})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
