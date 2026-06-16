import io
import os
import hmac
import hashlib
import json
import tempfile
import asyncio
import urllib.request
from datetime import datetime

import razorpay
import requests as http_requests
import fitz  # PyMuPDF
from PIL import Image
import ctypes
import ctypes.util

from flask import Flask, request, jsonify, send_from_directory, Response, render_template_string
from flask_cors import CORS

from asn1crypto import pem, x509 as asn1_x509
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature, EmbeddedPdfSignature
from pyhanko_certvalidator import ValidationContext

# Help pyzbar find zbar on Railway/nix
try:
    ctypes.CDLL('libzbar.so.0')
except:
    try:
        ctypes.CDLL('/root/.nix-profile/lib/libzbar.so.0')
    except:
        pass
from pyzbar.pyzbar import decode

# ── APP INIT ──────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# Razorpay client
rzp = razorpay.Client(
    auth=(os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET"))
)

# ── CCA CERTS FOLDER ─────────────────────────────────────
CERTS_FOLDER = os.path.join(os.path.dirname(__file__), "certs")


# ── SIGNATURE VALIDATOR HELPERS ───────────────────────────

def load_trust_roots():
    """Load all CCA/CA root certificates from the /certs folder."""
    certs = []
    if not os.path.exists(CERTS_FOLDER):
        return certs
    for fname in os.listdir(CERTS_FOLDER):
        if not fname.lower().endswith(('.cer', '.pem', '.crt')):
            continue
        fpath = os.path.join(CERTS_FOLDER, fname)
        try:
            with open(fpath, 'rb') as f:
                data = f.read()
            if pem.detect(data):
                _, _, der = pem.unarmor(data)
                certs.append(asn1_x509.Certificate.load(der))
            else:
                certs.append(asn1_x509.Certificate.load(data))
        except Exception as e:
            print(f"[WARN] Could not load cert {fname}: {e}")
    return certs


def get_signer_info(embedded_sig):
    """Extract human-readable signer details from embedded signature."""
    info = {
        "signer_name": "Unknown",
        "organization": None,
        "email": None,
        "cert_valid_from": None,
        "cert_valid_to": None,
        "cert_issuer": None,
        "signing_time": None,
        "field_name": embedded_sig.field_name,
    }
    try:
        cert = embedded_sig.signer_cert
        if cert is None:
            return info
        subject = cert.subject
        for rdn in subject.chosen:
            for atv in rdn:
                oid = atv['type'].dotted
                val = str(atv['value'].chosen) if hasattr(atv['value'], 'chosen') else str(atv['value'])
                if oid == '2.5.4.3':
                    info['signer_name'] = val
                elif oid == '2.5.4.10':
                    info['organization'] = val
                elif oid == '1.2.840.113549.1.9.1':
                    info['email'] = val
        validity = cert['tbs_certificate']['validity']
        info['cert_valid_from'] = validity['not_before'].native.strftime('%d %b %Y') if validity['not_before'].native else None
        info['cert_valid_to'] = validity['not_after'].native.strftime('%d %b %Y') if validity['not_after'].native else None
        issuer = cert.issuer
        for rdn in issuer.chosen:
            for atv in rdn:
                if atv['type'].dotted == '2.5.4.3':
                    info['cert_issuer'] = str(atv['value'].chosen) if hasattr(atv['value'], 'chosen') else str(atv['value'])
        ts = embedded_sig.self_reported_timestamp
        if ts:
            info['signing_time'] = ts.strftime('%d %b %Y, %I:%M %p')
    except Exception as e:
        print(f"[WARN] signer_info extraction error: {e}")
    return info


def validate_pdf_file(pdf_bytes):
    """Core validation logic. Returns a dict with all signature results."""
    result = {
        "has_signatures": False,
        "signature_count": 0,
        "signatures": [],
        "overall_valid": False,
        "error": None,
    }
    try:
        reader = PdfFileReader(io.BytesIO(pdf_bytes), strict=False)
        embedded_sigs = reader.embedded_signatures
        if not embedded_sigs:
            result["error"] = "no_signatures"
            return result
        result["has_signatures"] = True
        result["signature_count"] = len(embedded_sigs)
        trust_roots = load_trust_roots()
        if trust_roots:
            vc = ValidationContext(trust_roots=trust_roots, allow_fetching=True)
        else:
            vc = ValidationContext(allow_fetching=True)
        all_valid = True
        for sig in embedded_sigs:
            signer_info = get_signer_info(sig)
            sig_result = {
                "field_name": signer_info["field_name"],
                "signer_name": signer_info["signer_name"],
                "organization": signer_info["organization"],
                "email": signer_info["email"],
                "cert_valid_from": signer_info["cert_valid_from"],
                "cert_valid_to": signer_info["cert_valid_to"],
                "cert_issuer": signer_info["cert_issuer"],
                "signing_time": signer_info["signing_time"],
                "intact": False,
                "trusted": False,
                "status": "unknown",
                "status_detail": "",
            }
            try:
                status = validate_pdf_signature(sig, signer_validation_context=vc)
                sig_result["intact"] = status.intact
                sig_result["trusted"] = status.trusted
                sig_result["coverage"] = str(status.coverage) if status.coverage else None
                if status.intact and status.trusted:
                    sig_result["status"] = "valid"
                    sig_result["status_detail"] = "Signature is valid and trusted"
                elif status.intact and not status.trusted:
                    sig_result["status"] = "intact_untrusted"
                    sig_result["status_detail"] = "Signature is mathematically intact but the certificate is not in a trusted chain. Install CCA India root certificate."
                    all_valid = False
                elif not status.intact:
                    sig_result["status"] = "invalid"
                    sig_result["status_detail"] = "Signature is INVALID — document may have been modified after signing."
                    all_valid = False
            except Exception as e:
                sig_result["status"] = "error"
                sig_result["status_detail"] = f"Validation error: {str(e)}"
                all_valid = False
            result["signatures"].append(sig_result)
        result["overall_valid"] = all_valid
    except Exception as e:
        result["error"] = str(e)
    return result


# ── EMBED HTML ────────────────────────────────────────────
EMBED_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PDF Digital Signature Validator - Free | SalaryBit</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; background: #f5f7fa; color: #222; min-height: 100vh; }
header { background: linear-gradient(135deg, #1a237e, #283593); color: #fff; padding: 28px 20px 22px; text-align: center; }
header h1 { font-size: 1.45rem; margin-bottom: 6px; }
header p { font-size: 0.93rem; opacity: 0.88; }
.badge { display: inline-block; background: #43a047; color: #fff; font-size: 0.75rem; font-weight: 700; padding: 3px 12px; border-radius: 20px; margin-top: 10px; text-transform: uppercase; }
.container { max-width: 700px; margin: 0 auto; padding: 28px 16px 60px; }
.upload-zone { border: 2.5px dashed #9fa8da; border-radius: 14px; background: #fff; padding: 40px 20px; text-align: center; cursor: pointer; transition: border-color 0.2s, background 0.2s; margin-bottom: 20px; }
.upload-zone:hover, .upload-zone.dragover { border-color: #3949ab; background: #f0f2ff; }
.upload-icon { font-size: 3rem; margin-bottom: 12px; }
.upload-zone h2 { font-size: 1.1rem; color: #1a237e; margin-bottom: 8px; }
.upload-zone p { font-size: 0.88rem; color: #666; margin-bottom: 4px; }
.file-name { margin-top: 14px; font-size: 0.9rem; font-weight: 600; color: #3949ab; }
.btn-file { display: inline-block; margin-top: 16px; padding: 10px 28px; background: #3949ab; color: #fff; border-radius: 6px; font-size: 0.95rem; font-weight: 600; cursor: pointer; border: none; }
.btn-validate { width: 100%; padding: 14px; background: #1a237e; color: #fff; border: none; border-radius: 8px; font-size: 1rem; font-weight: 700; cursor: pointer; transition: background 0.2s; margin-bottom: 20px; }
.btn-validate:hover { background: #283593; }
.btn-validate:disabled { background: #9fa8da; cursor: not-allowed; }
#results { display: none; }
.overall-banner { border-radius: 10px; padding: 18px 20px; margin-bottom: 20px; display: flex; align-items: center; gap: 14px; }
.overall-banner.valid { background: #e8f5e9; border: 2px solid #43a047; }
.overall-banner.invalid { background: #fce4ec; border: 2px solid #e53935; }
.overall-banner.warning { background: #fff8e1; border: 2px solid #f9a825; }
.overall-icon { font-size: 2.2rem; }
.overall-text h3 { font-size: 1.05rem; margin-bottom: 4px; }
.overall-text p { font-size: 0.88rem; color: #555; }
.sig-card { background: #fff; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.07); padding: 20px 22px; margin-bottom: 16px; }
.sig-card h4 { font-size: 0.95rem; color: #1a237e; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1.5px solid #e8eaf6; }
.sig-status { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; font-size: 0.95rem; padding: 6px 14px; border-radius: 20px; margin-bottom: 14px; }
.sig-status.valid { background: #e8f5e9; color: #2e7d32; }
.sig-status.intact_untrusted { background: #fff8e1; color: #e65100; }
.sig-status.invalid { background: #fce4ec; color: #c62828; }
.sig-status.error { background: #f5f5f5; color: #555; }
.sig-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.sig-detail { font-size: 0.85rem; }
.sig-detail .label { color: #888; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
.sig-detail .val { font-weight: 600; color: #222; word-break: break-word; }
.status-detail-msg { margin-top: 12px; font-size: 0.88rem; background: #f5f7fa; border-radius: 6px; padding: 10px 14px; color: #444; }
.no-sig-box { background: #fff; border-radius: 10px; border: 2px solid #e0e0e0; padding: 30px; text-align: center; color: #666; }
.no-sig-box .icon { font-size: 2.5rem; margin-bottom: 10px; }
.loading { text-align: center; padding: 30px; display: none; }
.spinner { width: 40px; height: 40px; margin: 0 auto 14px; border: 4px solid #e8eaf6; border-top-color: #1a237e; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.reset-btn { background: none; border: 1.5px solid #9fa8da; color: #3949ab; padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 0.88rem; margin-top: 10px; }
.reset-btn:hover { background: #e8eaf6; }
.privacy-note { text-align: center; font-size: 0.8rem; color: #888; margin-top: 20px; }
footer { background: #1a237e; color: #cfd8dc; text-align: center; padding: 16px; font-size: 0.85rem; margin-top: 40px; }
footer a { color: #90caf9; text-decoration: none; }
@media(max-width:500px) { header h1 { font-size: 1.15rem; } .sig-detail-grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <h1>PDF Digital Signature Validator</h1>
  <p>Instantly check if signatures in any PDF are valid and trusted</p>
  <span class="badge">Free - Private - No Registration - Works for Form 16, ITR, GST and more</span>
</header>
<div class="container">
  <div id="uploader">
    <div class="upload-zone" id="dropZone">
      <div class="upload-icon">&#128196;</div>
      <h2>Drop your PDF here</h2>
      <p>Form 16 - ITR Acknowledgement - GST Certificate - Property Documents - Any signed PDF</p>
      <p>Max 10MB - PDF only</p>
      <button class="btn-file" onclick="document.getElementById('pdfInput').click()">Browse File</button>
      <input type="file" id="pdfInput" accept=".pdf" style="display:none">
      <div class="file-name" id="fileName"></div>
    </div>
    <button class="btn-validate" id="validateBtn" disabled onclick="validateFile()">Validate Signature</button>
    <p class="privacy-note">Your file is processed on-server and immediately discarded. Nothing is stored.</p>
  </div>
  <div class="loading" id="loading">
    <div class="spinner"></div>
    <p style="color:#555;">Validating signature chain...</p>
  </div>
  <div id="results"></div>
</div>
<footer>
  <p>2026 <a href="https://salarybit.in">SalaryBit.in</a> - Free personal finance and tax tools for India</p>
</footer>
<script>
var pdfInput = document.getElementById('pdfInput');
var validateBtn = document.getElementById('validateBtn');
var fileName = document.getElementById('fileName');
var dropZone = document.getElementById('dropZone');
var resultsDiv = document.getElementById('results');
var loadingDiv = document.getElementById('loading');
var uploaderDiv = document.getElementById('uploader');
var selectedFile = null;

pdfInput.addEventListener('change', function() {
  if (pdfInput.files[0]) selectFile(pdfInput.files[0]);
});

dropZone.addEventListener('dragover', function(e) { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', function() { dropZone.classList.remove('dragover'); });
dropZone.addEventListener('drop', function(e) {
  e.preventDefault(); dropZone.classList.remove('dragover');
  if (e.dataTransfer.files[0]) selectFile(e.dataTransfer.files[0]);
});

function selectFile(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) { alert('Please select a PDF file.'); return; }
  selectedFile = file;
  fileName.textContent = file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)';
  validateBtn.disabled = false;
}

function validateFile() {
  if (!selectedFile) return;
  uploaderDiv.style.display = 'none';
  loadingDiv.style.display = 'block';
  resultsDiv.style.display = 'none';
  var formData = new FormData();
  formData.append('pdf', selectedFile);
  fetch('/validate-signature', { method: 'POST', body: formData })
    .then(function(response) { return response.json(); })
    .then(function(data) { renderResults(data); })
    .catch(function(err) { renderError('Network error. Please try again.'); })
    .finally(function() { loadingDiv.style.display = 'none'; });
}

function renderResults(data) {
  resultsDiv.style.display = 'block';
  var html = '';
  if (data.error === 'no_signatures') {
    html = '<div class="no-sig-box"><div class="icon">&#128275;</div><h3 style="margin-bottom:8px;color:#444;">No Digital Signatures Found</h3><p>This PDF does not contain any embedded digital signatures.</p></div>';
  } else if (data.error) {
    html = '<div class="no-sig-box"><div class="icon">&#9888;</div><h3 style="margin-bottom:8px;color:#c62828;">Could Not Read PDF</h3><p>' + escHtml(data.error) + '</p></div>';
  } else {
    var bannerClass, bannerIcon, bannerTitle, bannerMsg;
    if (data.overall_valid) {
      bannerClass = 'valid'; bannerIcon = '&#9989;';
      bannerTitle = 'All Signatures Valid';
      bannerMsg = data.signature_count + ' signature(s) found - all intact and trusted.';
    } else {
      var hasIntact = false;
      for (var i = 0; i < data.signatures.length; i++) {
        if (data.signatures[i].status === 'intact_untrusted') { hasIntact = true; break; }
      }
      if (hasIntact) {
        bannerClass = 'warning'; bannerIcon = '&#9888;&#65039;';
        bannerTitle = 'Signature Intact but Certificate Not Trusted';
        bannerMsg = 'The document has not been altered, but the signing authority certificate is not trusted on this server. The signature itself is mathematically valid.';
      } else {
        bannerClass = 'invalid'; bannerIcon = '&#10060;';
        bannerTitle = 'Signature Invalid';
        bannerMsg = 'One or more signatures are invalid. The document may have been tampered with after signing.';
      }
    }
    html += '<div class="overall-banner ' + bannerClass + '"><div class="overall-icon">' + bannerIcon + '</div><div class="overall-text"><h3>' + bannerTitle + '</h3><p>' + bannerMsg + '</p></div></div>';
    for (var j = 0; j < data.signatures.length; j++) {
      var sig = data.signatures[j];
      var statusLabels = { valid: 'Valid and Trusted', intact_untrusted: 'Intact - Certificate Untrusted', invalid: 'Invalid', error: 'Could Not Validate' };
      var statusLabel = statusLabels[sig.status] || sig.status;
      html += '<div class="sig-card"><h4>Signature ' + (j+1) + (sig.field_name ? ' - Field: ' + escHtml(sig.field_name) : '') + '</h4>';
      html += '<div class="sig-status ' + sig.status + '">' + statusLabel + '</div>';
      html += '<div class="sig-detail-grid">';
      html += sigDetail('Signer', sig.signer_name);
      if (sig.organization) html += sigDetail('Organisation', sig.organization);
      if (sig.email) html += sigDetail('Email', sig.email);
      if (sig.signing_time) html += sigDetail('Signed On', sig.signing_time);
      if (sig.cert_issuer) html += sigDetail('Issued By', sig.cert_issuer);
      if (sig.cert_valid_from && sig.cert_valid_to) html += sigDetail('Certificate Valid', sig.cert_valid_from + ' to ' + sig.cert_valid_to);
      html += '</div>';
      html += '<div class="status-detail-msg">' + escHtml(sig.status_detail) + '</div></div>';
    }
  }
  html += '<div style="text-align:center;margin-top:20px;"><button class="reset-btn" onclick="resetTool()">Validate Another PDF</button></div>';
  resultsDiv.innerHTML = html;
}

function sigDetail(label, val) {
  if (!val) return '';
  return '<div class="sig-detail"><div class="label">' + label + '</div><div class="val">' + escHtml(String(val)) + '</div></div>';
}

function renderError(msg) {
  resultsDiv.style.display = 'block';
  resultsDiv.innerHTML = '<div class="no-sig-box"><div class="icon">&#9888;</div><h3 style="margin-bottom:8px;color:#c62828;">Error</h3><p>' + escHtml(msg) + '</p><button class="reset-btn" onclick="resetTool()" style="margin-top:16px;">Try Again</button></div>';
}

function escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function resetTool() {
  selectedFile = null;
  fileName.textContent = '';
  validateBtn.disabled = true;
  pdfInput.value = '';
  resultsDiv.style.display = 'none';
  resultsDiv.innerHTML = '';
  uploaderDiv.style.display = 'block';
}
</script>
</body>
</html>"""


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
        return jsonify({"order_id": order["id"], "amount": order["amount"], "currency": order["currency"]})
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
        return jsonify({"success": False, "error": "No QR code found in this PDF. A refund will be processed within 24 hours."})
    return jsonify({"success": True, "qr_strings": results, "count": len(results)})


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
                    results.append({"value": decoded, "doc_number": parts[0], "page": page_num + 1, "label": f"Page {page_num + 1}"})
            except Exception as e:
                print(f"Image decode error page {page_num + 1}: {e}")
                continue
    doc.close()
    return results


# ── CREATE RESUME ORDER ───────────────────────────────────
@app.route("/api/create-resume-order", methods=["POST", "OPTIONS"])
def create_resume_order():
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": 9900,
            "currency": "INR",
            "receipt": f"resume_{os.urandom(4).hex()}",
        })
        return jsonify({"order_id": order["id"], "amount": order["amount"], "currency": order["currency"], "razorpay_key": os.environ.get("RAZORPAY_KEY_ID")})
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
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {groq_key}"},
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


# ── FOOTBALL PROXY ────────────────────────────────────────
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


# ── FIFA PAGE ─────────────────────────────────────────────
@app.route('/fifa-2026')
def fifa():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fifa-2026.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        content_html = f.read()
    return Response(content_html, mimetype='text/html')


# ── PDF SIGNATURE VALIDATOR ───────────────────────────────
@app.route('/validate-signature', methods=['GET'])
def validate_signature_page():
    # FIXED: Use Response() instead of render_template_string() to prevent
    # Jinja2 from misinterpreting JavaScript curly braces as template variables,
    # which caused the "Uncaught SyntaxError: Unexpected identifier" error.
    return Response(EMBED_HTML, mimetype='text/html')


@app.route('/validate-signature', methods=['POST'])
def validate_signature():
    if 'pdf' not in request.files:
        return jsonify({"error": "No file uploaded. Send PDF as 'pdf' field."}), 400
    f = request.files['pdf']
    if not f.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Only PDF files are supported."}), 400
    pdf_bytes = f.read()
    if len(pdf_bytes) == 0:
        return jsonify({"error": "Uploaded file is empty."}), 400
    result = validate_pdf_file(pdf_bytes)
    result["filename"] = f.filename
    result["file_size_kb"] = round(len(pdf_bytes) / 1024, 1)
    return jsonify(result)


# ── HEALTH CHECK ──────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "SalaryBit API"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
