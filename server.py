import os
import hmac
import hashlib
import tempfile
import ctypes
import io
import razorpay
from flask import Flask, request, jsonify
from flask_cors import CORS
import fitz  # PyMuPDF
from PIL import Image

# Help pyzbar find zbar shared library on Railway/nix
for lib in ['libzbar.so.0', '/root/.nix-profile/lib/libzbar.so.0', '/usr/lib/libzbar.so.0']:
    try:
        ctypes.CDLL(lib)
        break
    except:
        continue

from pyzbar.pyzbar import decode

app = Flask(__name__)
CORS(app)

rzp = razorpay.Client(
    auth=(os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET"))
)


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


def decode_qr_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    results = []
    seen = set()

    print(f"PDF opened: {doc.page_count} pages")

    for page_num in range(doc.page_count):
        page = doc[page_num]

        # Method 1: Extract embedded images
        img_list = page.get_images(full=True)
        print(f"Page {page_num+1}: {len(img_list)} embedded images")

        for img_info in img_list:
            xref = img_info[0]
            try:
                base_img = doc.extract_image(xref)
                img = Image.open(io.BytesIO(base_img["image"]))
                print(f"  Image size: {img.width}x{img.height}")

                for scale in [1, 2, 4, 8, 12]:
                    w = img.width * scale
                    h = img.height * scale
                    scaled = img.resize((w, h), Image.NEAREST)
                    found = decode(scaled)
                    if found:
                        for qr in found:
                            decoded = qr.data.decode("utf-8", errors="replace")
                            print(f"  QR found at scale {scale}: {decoded[:50]}")
                            if "+++" in decoded and decoded not in seen:
                                seen.add(decoded)
                                parts = decoded.split("+++", 1)
                                results.append({
                                    "value": decoded,
                                    "doc_number": parts[0],
                                    "page": page_num + 1,
                                    "label": f"Page {page_num + 1}"
                                })
                        break

            except Exception as e:
                print(f"  Image error: {e}")
                continue

        # Method 2: Render page as high-res image and scan
        if not results:
            try:
                mat = fitz.Matrix(4, 4)  # 4x zoom = ~288 DPI
                pix = page.get_pixmap(matrix=mat)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                print(f"Page {page_num+1} rendered: {img.width}x{img.height}")

                found = decode(img)
                if found:
                    for qr in found:
                        decoded = qr.data.decode("utf-8", errors="replace")
                        print(f"  Rendered QR found: {decoded[:50]}")
                        if "+++" in decoded and decoded not in seen:
                            seen.add(decoded)
                            parts = decoded.split("+++", 1)
                            results.append({
                                "value": decoded,
                                "doc_number": parts[0],
                                "page": page_num + 1,
                                "label": f"Page {page_num + 1}"
                            })
            except Exception as e:
                print(f"  Render error: {e}")

    doc.close()
    print(f"Total QR results: {len(results)}")
    return results


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "SalaryBit QR Decoder"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
