import io
import os
import hmac
import hashlib
import json
import tempfile
import asyncio
import urllib.request
import urllib.error
import base64
import uuid
import time as _time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import razorpay
import requests as http_requests
import fitz  # PyMuPDF
from PIL import Image
import ctypes
import ctypes.util

from flask import Flask, request, jsonify, send_from_directory, Response, render_template_string
from flask_cors import CORS

# ── ADD: new imports for subscription scan ──────────────────
import pdfplumber
import re
from collections import defaultdict
from pdfminer.pdfdocument import PDFPasswordIncorrect, PDFEncryptionError
try:
    from pdfplumber.utils.exceptions import PdfminerException
except ImportError:
    # Fallback for environments where the installed pdfplumber build is
    # missing this submodule (e.g. stale build cache, or a local file/folder
    # named "pdfplumber" shadowing the real package on the import path).
    # This should not happen with pdfplumber==0.11.4 as pinned in
    # requirements.txt — if you're seeing this fallback in production logs,
    # check for: (1) a file/folder literally named "pdfplumber" in the repo
    # root, (2) a stale Railway build cache (redeploy without cache).
    print("WARNING: pdfplumber.utils.exceptions.PdfminerException not found — "
          "using a fallback exception class. PDF password-protection "
          "detection for bank statements will be less precise until this "
          "is fixed. See comment above this line for likely causes.")
    class PdfminerException(Exception):
        pass

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


# ── SUBSCRIPTION SCAN HELPERS ─────────────────────────────


class PDFPasswordProtectedError(Exception):
    """Raised when a PDF is encrypted and either no password or the wrong password was supplied."""
    pass


# A handful of banks export multi-year statements as one PDF. Table extraction
# is the actual slow part of the free scan (no Claude call happens here), so
# cap how many pages we walk per PDF — recurring charges show up easily within
# this many pages/months, and this keeps one huge upload from stalling the
# whole request for everyone.
MAX_PDF_PAGES = 60


def extract_transactions_from_pdf(pdf_path, password=None):
    """Generic transaction table extraction - works across bank formats."""
    all_rows = []
    try:
        pdf_obj = pdfplumber.open(pdf_path, password=password) if password else pdfplumber.open(pdf_path)
    except (PDFPasswordIncorrect, PDFEncryptionError):
        raise PDFPasswordProtectedError()
    except PdfminerException as e:
        cause = e.__cause__ or (e.args[0] if e.args else None)
        if isinstance(cause, (PDFPasswordIncorrect, PDFEncryptionError)):
            raise PDFPasswordProtectedError()
        err_str = str(e).lower() or str(cause).lower()
        if "password" in err_str or "encrypt" in err_str or "incorrect" in err_str:
            raise PDFPasswordProtectedError() from e
        raise
    except Exception as e:
        err_str = str(e).lower()
        if "password" in err_str or "encrypt" in err_str or "incorrect" in err_str:
            raise PDFPasswordProtectedError() from e
        raise

    with pdf_obj as pdf:
        for page_num, page in enumerate(pdf.pages):
            if page_num >= MAX_PDF_PAGES:
                print(f"[subscription-scan] {pdf_path}: capped at {MAX_PDF_PAGES} pages "
                      f"(PDF has more) — scanning the rest would be slow and recurring "
                      f"charges are already well represented in this range.")
                break
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                header = [str(c).strip().lower() if c else "" for c in table[0]]
                has_date = any('date' in h for h in header)
                has_narration = any(
                    k in cell for cell in header
                    for k in ['narration', 'description', 'particulars', 'details']
                )
                if not (has_date and has_narration):
                    continue
                for row in table[1:]:
                    if row and any(row):
                        all_rows.append(row)
    return all_rows


IMAGE_MEDIA_TYPES = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.png': 'image/png', '.webp': 'image/webp',
}


class ImageExtractionError(Exception):
    """Raised when Claude vision could not read transactions from an image."""
    pass


def extract_transactions_from_image(image_path, media_type):
    """
    Uses Claude vision to read a bank-statement / UPI-app screenshot photo
    and pull out debit transactions in the same [date, narration, amount, ""]
    row shape that extract_transactions_from_pdf() produces, so it can flow
    through the same classify_statement_rows() pipeline.
    """
    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    if not claude_key:
        raise ImageExtractionError("Server not configured for photo scanning.")

    with open(image_path, "rb") as fh:
        img_b64 = base64.b64encode(fh.read()).decode("utf-8")

    prompt = (
        "This image is a screenshot or photo of an Indian bank statement, UPI app "
        "'manage mandates' screen, or transaction list. Extract every DEBIT / "
        "withdrawal / outgoing transaction visible (ignore credits/deposits/incoming). "
        "For each one give: date (as shown), narration/merchant text exactly as shown, "
        "and amount (a plain number, no currency symbol or commas). "
        "Output ONLY a valid JSON array, no markdown, no preamble, like: "
        '[{"date": "01/06/2026", "narration": "ACH D-NETFLIX", "amount": 649}]. '
        "If you cannot find any transactions, output []."
    )

    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 2048,
        "temperature": 0,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
                {"type": "text", "text": prompt}
            ]
        }]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": claude_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        raw = result["content"][0]["text"]
        clean = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean)
    except Exception as e:
        print(f"extract_transactions_from_image error: {e}")
        raise ImageExtractionError("Could not read transactions from this photo. Try a clearer, well-lit screenshot.")

    rows = []
    for item in parsed:
        date_val = str(item.get("date", "")).strip()
        narration = str(item.get("narration", "")).strip()
        amount = item.get("amount", "")
        if not date_val or not narration:
            continue
        rows.append([date_val, narration, str(amount), ""])
    return rows


def parse_statement_date(s):
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_statement_amount(s):
    if not s:
        return 0.0
    s = re.sub(r'[^\d.]', '', s)
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def merchant_signature(narration):
    s = narration.upper()
    s = re.sub(r'\b\d{4,}\b', '', s)
    s = re.sub(r'-\d+$', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def classify_statement_rows(raw_rows):
    txns = []
    for row in raw_rows:
        if len(row) < 4:
            continue
        date_str, narration = row[0], row[1]
        withdrawal = parse_statement_amount(row[2]) if len(row) > 2 else 0
        d = parse_statement_date(date_str)
        if not d or not narration or withdrawal <= 0:
            continue
        txns.append({
            "date": d,
            "narration": narration.strip(),
            "amount": withdrawal,
            "signature": merchant_signature(narration),
        })
    return txns


SUBSCRIPTION_HINTS = [
    'netflix', 'spotify', 'hotstar', 'prime', 'youtube', 'google play',
    'playstore', 'truecaller', 'twitter', ' x premium', 'zee5', 'sonyliv',
    'jiocinema', 'apple', 'icloud', 'microsoft', 'adobe', 'canva',
    'subscription', 'autopay', 'ach d', 'sip', 'mandate', 'insurance',
    'premium', 'membership', 'gym', 'lic ', 'mutual fund'
]
NOISE_HINTS = [
    'swiggy', 'zomato', 'atm wdl', 'amazon retail', 'flipkart',
    'uber', 'ola', 'irctc', 'fuel', 'petrol', 'grocery', 'bigbasket'
]


def detect_recurring_charges(txns, amount_tolerance=0.05):
    groups = defaultdict(list)
    for t in txns:
        groups[t["signature"]].append(t)

    results = []
    for sig, items in groups.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda x: x["date"])
        amounts = [i["amount"] for i in items]
        avg_amount = sum(amounts) / len(amounts)
        if avg_amount == 0:
            continue
        if not all(abs(a - avg_amount) / avg_amount <= amount_tolerance for a in amounts):
            continue

        intervals = [(items[i]["date"] - items[i-1]["date"]).days for i in range(1, len(items))]
        avg_interval = sum(intervals) / len(intervals) if intervals else 0
        interval_variance = (max(intervals) - min(intervals)) if intervals else 999

        frequency = None
        if 25 <= avg_interval <= 35 and interval_variance <= 6:
            frequency = "monthly"
        elif 80 <= avg_interval <= 100 and interval_variance <= 10:
            frequency = "quarterly"
        elif 350 <= avg_interval <= 380 and interval_variance <= 15:
            frequency = "yearly"
        if frequency is None:
            continue

        sig_lower = sig.lower()
        is_known_subscription = any(h in sig_lower for h in SUBSCRIPTION_HINTS)
        is_known_noise = any(h in sig_lower for h in NOISE_HINTS)
        if is_known_noise and not is_known_subscription:
            continue
        if len(items) < 3 and not is_known_subscription:
            continue

        multiplier = {"monthly": 12, "quarterly": 4, "yearly": 1}.get(frequency, 1)
        annual_cost = round(avg_amount * multiplier, 2)

        results.append({
            "narration_sample": items[-1]["narration"],
            "amount": round(avg_amount, 2),
            "occurrences": len(items),
            "frequency": frequency,
            "first_seen": items[0]["date"].strftime("%d %b %Y"),
            "last_seen": items[-1]["date"].strftime("%d %b %Y"),
            "annual_cost": annual_cost,
            "confidence": "high" if is_known_subscription else "medium",
        })

    results.sort(key=lambda x: x["annual_cost"], reverse=True)
    return results


def guess_payment_method(narration):
    """Heuristic fallback so every item always has a payment_method, even if Claude's
    classification is missing/unparseable."""
    s = narration.upper()
    if 'NACH' in s or re.search(r'\bACH\b', s):
        return 'nach'
    if 'UPI' in s or 'MANDATE' in s:
        return 'upi'
    if re.search(r'\bXX+\d{2,4}\b', s) or 'CARD' in s:
        return 'card'
    return 'other'


def identify_merchants_claude(recurring_list):
    """
    Uses ANTHROPIC_API_KEY to identify merchant narrations via Claude,
    same urllib.request pattern as the rest of this file (no SDK dependency).

    Returns (enriched_list, ai_failed) — ai_failed is True when the Claude
    call itself failed or its response didn't parse, so the caller can
    surface a visible warning instead of silently shipping an "Unknown"
    report to a paying customer.
    """
    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    if not claude_key or not recurring_list:
        fallback = [
            {**r, "identified_as": "Unknown - check manually",
             "category": "Unknown",
             "how_to_cancel": "Check NPCI UPI Autopay portal or your bank app",
             "payment_method": guess_payment_method(r["narration_sample"])}
            for r in recurring_list
        ]
        return fallback, bool(recurring_list) and not claude_key

    txn_summaries = [
        {"narration": r["narration_sample"], "amount": r["amount"], "frequency": r["frequency"]}
        for r in recurring_list
    ]
    prompt = f"""You are helping an Indian user understand recurring bank charges auto-detected from their statement.

Rules:
- Indian context: UPI/card/ACH narrations from Indian bank statements
- "ARHA MEDIA" = Aha (Telugu/Tamil OTT app), generic "playstore" VPAs = Google Play Store app billing, "ACH D-NETFLIX" = Netflix, etc.
- If unclear, say "Unclear - check [merchant] directly" rather than guessing
- payment_method must be exactly one of: "upi" (UPI AutoPay / VPA mandate), "card" (debit/credit card autopay or standing instruction), "nach" (NACH/ACH bank mandate, typically SIPs/insurance/EMIs), "other" (can't tell)
- how_to_cancel should be a short, specific one-line instruction naming where to go (e.g. "NPCI mandate portal" for upi, "Netbanking > Manage Standing Instructions" for card)
- Output ONLY valid JSON array, no markdown, no preamble

Transactions:
{json.dumps(txn_summaries)}

Output format:
[{{"narration": "...", "identified_as": "...", "category": "OTT/Streaming|Telecom|Cloud/Software|Insurance|Investment SIP|Unknown|Other", "payment_method": "upi|card|nach|other", "how_to_cancel": "short instruction"}}]"""

    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 4000,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": claude_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )
    ai_failed = False
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        raw = result["content"][0]["text"]
        clean = raw.replace("```json", "").replace("```", "").strip()
        identifications = json.loads(clean)
    except Exception as e:
        print(f"identify_merchants_claude error: {e}")
        identifications = []
        ai_failed = True

    id_map = {i["narration"]: i for i in identifications}
    enriched = []
    for r in recurring_list:
        match = id_map.get(r["narration_sample"], {})
        payment_method = match.get("payment_method")
        if payment_method not in ("upi", "card", "nach", "other"):
            payment_method = guess_payment_method(r["narration_sample"])
        enriched.append({
            **r,
            "identified_as": match.get("identified_as", "Unknown - check manually"),
            "category": match.get("category", "Unknown"),
            "how_to_cancel": match.get("how_to_cancel", "Check NPCI UPI Autopay or your bank app"),
            "payment_method": payment_method,
        })
    return enriched, ai_failed


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


@app.route('/qr-decoder', methods=['GET'])
def qr_decoder_page():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qr-decoder.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        content_html = f.read()
    return Response(content_html, mimetype='text/html')


# ── CREATE ORDER ──────────────────────────────────────────
@app.route("/api/create-order", methods=["POST", "OPTIONS"])
def create_order():
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": 9900,  # Rs 99 (standardized across all paid tools)
            "currency": "INR",
            "receipt": f"qr_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "razorpay_key": os.environ.get("RAZORPAY_KEY_ID")
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
        return jsonify({"success": False, "error": "No QR code found in this PDF. A refund will be processed within 24 hours."})
    return jsonify({"success": True, "qr_strings": results, "count": len(results)})


# ── QR DECODE LOGIC ───────────────────────────────────────
def decode_qr_from_pdf(pdf_path):
    # Skip images larger than 500x500 — those are property photos, not QR
    # codes. Loading + upscaling a large photo up to 12x is what previously
    # caused a SIGKILL OOM crash on Railway, silently losing the request
    # after payment had already succeeded.
    MAX_PIXELS = 500 * 500
    MIN_SIZE = 50

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
                iw = base_img["width"]
                ih = base_img["height"]
                if iw * ih > MAX_PIXELS or iw < MIN_SIZE or ih < MIN_SIZE:
                    continue
                img = Image.open(io.BytesIO(base_img["image"]))
                decoded = None
                for scale in [1, 4, 8, 12]:
                    w = min(img.width * scale, 1200)
                    h = min(img.height * scale, 1200)
                    scaled = img.resize((w, h), Image.NEAREST)
                    found = decode(scaled)
                    del scaled
                    if found:
                        decoded = found[0].data.decode("utf-8", errors="replace")
                        break
                del img
                if decoded and "+++" in decoded and decoded not in seen:
                    seen.add(decoded)
                    parts = decoded.split("+++", 1)
                    results.append({"value": decoded, "doc_number": parts[0], "page": page_num + 1, "label": f"Page {page_num + 1}"})
            except Exception as e:
                print(f"Image decode error page {page_num + 1}: {e}")
                continue
    doc.close()
    return results


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


# ── SUBSCRIPTION LEAK FINDER ──────────────────────────────

SUBSCRIPTION_SCAN_PRICE_PAISE = 9900  # Rs 99

# In-memory cache: scan_id -> {"recurring": [...], "ts": epoch_seconds}
# Holds the (already-detected, not-yet-AI-identified) recurring charge list
# between the free scan and the paid unlock, so unlock is a single fast
# Claude call instead of re-parsing the statement.
_SUBSCRIPTION_SCAN_CACHE = {}
_SCAN_CACHE_TTL = 1800  # 30 minutes


def _scan_cache_put(recurring_list):
    _scan_cache_gc()
    scan_id = uuid.uuid4().hex
    _SUBSCRIPTION_SCAN_CACHE[scan_id] = {"recurring": recurring_list, "ts": _time.time()}
    return scan_id


def _scan_cache_pop(scan_id):
    entry = _SUBSCRIPTION_SCAN_CACHE.pop(scan_id, None)
    if not entry:
        return None
    if _time.time() - entry["ts"] > _SCAN_CACHE_TTL:
        return None
    return entry["recurring"]


def _scan_cache_gc():
    now = _time.time()
    expired = [k for k, v in _SUBSCRIPTION_SCAN_CACHE.items() if now - v["ts"] > _SCAN_CACHE_TTL]
    for k in expired:
        _SUBSCRIPTION_SCAN_CACHE.pop(k, None)


# ── GENERIC CLAUDE PROXY (for client-side AI tools like MF Analyzer Bot) ──
_claude_proxy_hits = defaultdict(list)
CLAUDE_PROXY_LIMIT = 20       # max requests
CLAUDE_PROXY_WINDOW = 3600    # per hour, per IP

@app.route('/api/claude-proxy', methods=['POST', 'OPTIONS'])
def claude_proxy():
    if request.method == "OPTIONS":
        return "", 200

    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    if not claude_key:
        return jsonify({"error": "Server not configured. Missing ANTHROPIC_API_KEY."}), 500

    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
    now = _time.time()
    hits = _claude_proxy_hits[ip]
    hits[:] = [t for t in hits if now - t < CLAUDE_PROXY_WINDOW]
    if len(hits) >= CLAUDE_PROXY_LIMIT:
        return jsonify({"error": "Rate limit reached. Please try again later."}), 429
    hits.append(now)

    body = request.get_json(silent=True) or {}
    messages = body.get("messages")
    if not messages:
        return jsonify({"error": "Missing messages in request body"}), 400

    requested_max_tokens = min(int(body.get("max_tokens") or 1000), 8000)

    # Calls above this threshold are the paid analysis/report generations
    # (MF Analyzer's CAS analysis + Wealth Report). The free chat feature
    # only ever requests 1000, so it's unaffected. Previously this proxy had
    # no payment check at all for these — anyone could call it directly and
    # get the paid output without ever paying.
    FREE_TIER_MAX_TOKENS = 1200
    if requested_max_tokens > FREE_TIER_MAX_TOKENS:
        order_id = body.get("razorpay_order_id")
        payment_id = body.get("razorpay_payment_id")
        signature = body.get("razorpay_signature")
        if not all([order_id, payment_id, signature]):
            return jsonify({"error": "Payment verification required for this request."}), 402
        expected = hmac.new(
            os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256
        ).hexdigest()
        if expected != signature:
            return jsonify({"error": "Payment verification failed."}), 402

    payload = json.dumps({
        "model": body.get("model") or "claude-sonnet-4-6",
        "max_tokens": requested_max_tokens,
        "messages": messages
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": claude_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return jsonify(result)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"claude_proxy upstream error {e.code}: {err_body}")
        return jsonify({"error": "Upstream error"}), e.code
    except Exception as e:
        print(f"claude_proxy error: {e}")
        return jsonify({"error": str(e)}), 500


# ── MF ANALYZER BOT — CREATE ORDER ────────────────────────
MF_REPORT_AMOUNT = 9900  # ₹99 one-time full report (standardized across all paid tools)

@app.route("/api/create-mf-order", methods=["POST", "OPTIONS"])
def create_mf_order():
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": MF_REPORT_AMOUNT,  # never trust client amount
            "currency": "INR",
            "receipt": f"mf_report_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "razorpay_key": os.environ.get("RAZORPAY_KEY_ID")
        })
    except Exception as e:
        print(f"create-mf-order error: {e}")
        return jsonify({"error": str(e)}), 500


# ── MF ANALYZER BOT — VERIFY PAYMENT ──────────────────────
@app.route("/api/verify-mf-payment", methods=["POST", "OPTIONS"])
def verify_mf_payment():
    """Matches existing verify_and_decode() HMAC pattern exactly."""
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")
    if not all([order_id, payment_id, signature]):
        return jsonify({"success": False, "error": "Missing required fields."}), 400

    body = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    if expected != signature:
        return jsonify({"success": False, "error": "Payment verification failed."}), 400

    return jsonify({"success": True})


def _process_statement_file(file_storage, pdf_password):
    """
    Save one uploaded file to disk and extract its rows. Designed to run inside
    a worker thread so multiple files — especially photos, which each need a
    network round-trip to Claude vision — are processed concurrently instead
    of one after another, which is what used to make multi-file scans slow.
    Returns a dict describing the outcome; never raises.
    """
    filename = file_storage.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    tmp_path = None
    try:
        if ext == '.pdf':
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = tmp.name
                file_storage.save(tmp_path)
            rows = extract_transactions_from_pdf(tmp_path, password=pdf_password)
            return {"ok": True, "rows": rows, "tmp_path": tmp_path}
        elif ext in IMAGE_MEDIA_TYPES:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp_path = tmp.name
                file_storage.save(tmp_path)
            rows = extract_transactions_from_image(tmp_path, IMAGE_MEDIA_TYPES[ext])
            return {"ok": True, "rows": rows, "tmp_path": tmp_path}
        else:
            return {
                "ok": False, "tmp_path": tmp_path, "unsupported": True,
                "error": f"Unsupported file type: {filename}. Upload a PDF or a photo/screenshot (JPG, PNG)."
            }
    except PDFPasswordProtectedError:
        return {"ok": False, "tmp_path": tmp_path, "password_protected": True}
    except ImageExtractionError as e:
        return {"ok": False, "tmp_path": tmp_path, "error": str(e)}


@app.route('/subscription-leak-finder', methods=['GET'])
def subscription_leak_finder_page():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'subscription-leak-finder.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        content_html = f.read()
    return Response(content_html, mimetype='text/html')


@app.route('/api/subscription-scan', methods=['POST', 'OPTIONS'])
def subscription_scan():
    """
    FAST, free phase: extract + regex-detect recurring charges only — no Claude
    call here, which is what used to make people wait. Merchant names are never
    identified and never returned at this stage; only a headline total/count
    (the 'is this worth ₹49' teaser) plus a scan_id are sent back. The actual
    identified report is generated by /api/verify-subscription-payment, right
    after payment, using the cached recurring list (see _SUBSCRIPTION_SCAN_CACHE).
    Accepts one or more files under the 'statement' field — PDFs and/or
    photos/screenshots (jpg/png/webp).
    """
    if request.method == "OPTIONS":
        return "", 200

    files = request.files.getlist('statement')
    if not files:
        return jsonify({"error": "No file uploaded"}), 400

    pdf_password = (request.form.get('password') or '').strip() or None

    tmp_paths = []
    try:
        # Kick off all files at once — order of results below is preserved
        # (submission order), so error precedence (e.g. which file's password
        # error gets reported) is unchanged from the old sequential version.
        with ThreadPoolExecutor(max_workers=min(len(files), 4)) as executor:
            futures = [executor.submit(_process_statement_file, f, pdf_password) for f in files]
            results = [fut.result() for fut in futures]

        for res in results:
            if res.get("tmp_path"):
                tmp_paths.append(res["tmp_path"])

        all_raw_rows = []
        for res in results:
            if not res["ok"]:
                if res.get("password_protected"):
                    return jsonify({
                        "error": "password_protected",
                        "password_was_tried": bool(pdf_password),
                        "message": (
                            "That password didn't work, please double-check it."
                            if pdf_password else
                            "This PDF is password-protected."
                        ),
                        "subscriptions": []
                    }), 200
                status = 400 if res.get("unsupported") else 200
                return jsonify({"error": res["error"], "subscriptions": []}), status
            all_raw_rows.extend(res["rows"])

        if not all_raw_rows:
            return jsonify({
                "error": "Could not detect any transactions. Make sure this is a downloaded statement (not a scanned image with no visible table) or a clear, well-lit screenshot.",
                "subscriptions": []
            })

        txns = classify_statement_rows(all_raw_rows)
        recurring = detect_recurring_charges(txns)

        if not recurring:
            return jsonify({"subscriptions": [], "count": 0, "total_annual_cost": 0, "message": "No recurring subscriptions detected in this statement."})

        scan_id = _scan_cache_put(recurring)
        total_annual_cost = round(sum(r["annual_cost"] for r in recurring), 2)

        # Intentionally no merchant names / per-item detail here — that's the paid report.
        return jsonify({
            "scan_id": scan_id,
            "count": len(recurring),
            "total_annual_cost": total_annual_cost
        })
    except Exception as e:
        import traceback
        print(f"subscription_scan error: {type(e).__name__}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"{type(e).__name__}: {e}" if str(e) else f"{type(e).__name__} (no message)"}), 500
    finally:
        for p in tmp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass


@app.route('/api/create-subscription-scan-order', methods=['POST', 'OPTIONS'])
def create_subscription_scan_order():
    """Matches your existing create_resume_order() pattern exactly."""
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": SUBSCRIPTION_SCAN_PRICE_PAISE,
            "currency": "INR",
            "receipt": f"subscan_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "razorpay_key": os.environ.get("RAZORPAY_KEY_ID")
        })
    except Exception as e:
        print(f"create-subscription-scan-order error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/verify-subscription-payment', methods=['POST', 'OPTIONS'])
def verify_subscription_payment():
    """
    Matches your existing verify_and_decode() HMAC pattern exactly.
    Once payment is verified, if a scan_id is supplied we immediately run the
    (single, fast) Claude identification call on the already-detected recurring
    list and hand back the full report in the same response — no second wait
    for the user after paying.
    """
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")
    scan_id = data.get("scan_id")
    if not all([order_id, payment_id, signature]):
        return jsonify({"success": False, "error": "Missing required fields."}), 400

    body = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    if expected != signature:
        return jsonify({"success": False, "error": "Payment verification failed."}), 400

    if not scan_id:
        return jsonify({"success": True})

    recurring = _scan_cache_pop(scan_id)
    if recurring is None:
        return jsonify({
            "success": True,
            "error": "Your scan session expired. Payment succeeded, but please rescan your statement (you will not be charged again — contact support with this payment ID if needed) to view the report.",
            "payment_id": payment_id
        })

    enriched, ai_failed = identify_merchants_claude(recurring)
    response = {
        "success": True,
        "subscriptions": enriched,
        "total_annual_cost": round(sum(r["annual_cost"] for r in enriched), 2),
        "count": len(enriched)
    }
    if ai_failed:
        response["warning"] = (
            "We detected your recurring charges, but couldn't identify all the merchants "
            "automatically this time. Some entries below may show as \"Unknown\" — you can "
            "still see the amount, frequency, and cancel guidance for each. Refresh in a "
            "minute to try identification again, or contact support with this payment ID."
        )
        response["payment_id"] = payment_id
    return jsonify(response)


# ── PATIENCE PASSBOOK ──────────────────────────────────────
PASSBOOK_PRICE_PAISE = 9900  # Rs 99


@app.route('/patience-passbook', methods=['GET'])
def patience_passbook_page():
    """Serves the tool itself. Drop patience-passbook.html next to this
    server_railway.py file (same folder), same as fifa-2026.html and
    subscription-leak-finder.html are served."""
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'patience-passbook.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        content_html = f.read()
    return Response(content_html, mimetype='text/html')


@app.route("/api/create-passbook-order", methods=["POST", "OPTIONS"])
def create_passbook_order():
    """Matches your existing create_resume_order() pattern exactly."""
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": PASSBOOK_PRICE_PAISE,
            "currency": "INR",
            "receipt": f"passbook_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "razorpay_key": os.environ.get("RAZORPAY_KEY_ID")
        })
    except Exception as e:
        print(f"create-passbook-order error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/verify-passbook-payment", methods=["POST", "OPTIONS"])
def verify_passbook_payment():
    """
    Matches your existing verify_and_decode() HMAC pattern exactly.

    Unlike the QR/resume/subscription tools, there's no server-side PDF or
    Claude/Groq generation step here — every number in the passbook is
    already computed client-side with the same formulas as the free
    calculator. So once the signature checks out, we just confirm success;
    the frontend unlocks the printable report itself (window.print()).

    `email` is optional and only useful for your own lead list — right now
    it's just printed to the Railway logs. Swap the print() line for
    whatever you use to store leads (a Google Sheet via the Sheets API, a
    row in Postgres, an entry in Airtable — whatever's already wired up for
    your other tools).
    """
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}
    order_id   = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature  = data.get("razorpay_signature")
    email      = (data.get("email") or "").strip()

    if not all([order_id, payment_id, signature]):
        return jsonify({"success": False, "error": "Missing required fields."}), 400

    body = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    if expected != signature:
        return jsonify({"success": False, "error": "Payment verification failed."}), 400

    # TODO: replace this with wherever you actually store leads.
    print(f"[passbook] paid lead: {email or '(no email given)'} | payment_id={payment_id}")

    return jsonify({"success": True, "payment_id": payment_id})


# ── FAMILY PASSBOOK ─────────────────────────────────────────
# There is no free print path anymore: filling the form is free, but
# generating/printing the finished passbook is a paid unlock (same
# HMAC verify pattern as every other tool on this file). Nothing about
# what the person typed is ever sent to the server — payment is verified,
# then the browser's own window.print() renders the PDF locally.
FAMILY_PASSBOOK_PRICE_PAISE = 9900  # Rs 99


@app.route("/api/create-family-passbook-order", methods=["POST", "OPTIONS"])
def create_family_passbook_order():
    """Matches the existing create_*_order() pattern exactly."""
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": FAMILY_PASSBOOK_PRICE_PAISE,
            "currency": "INR",
            "receipt": f"fampass_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "razorpay_key": os.environ.get("RAZORPAY_KEY_ID")
        })
    except Exception as e:
        print(f"create-family-passbook-order error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/verify-family-passbook-payment", methods=["POST", "OPTIONS"])
def verify_family_passbook_payment():
    """
    Matches the existing verify_*_payment() HMAC pattern exactly. No PDF is
    generated here and no passbook content is ever sent to the server — once
    the signature checks out, the frontend unlocks window.print() itself.
    """
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")

    if not all([order_id, payment_id, signature]):
        return jsonify({"success": False, "error": "Missing required fields."}), 400

    body = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    if expected != signature:
        return jsonify({"success": False, "error": "Payment verification failed."}), 400

    print(f"[family-passbook] paid unlock | payment_id={payment_id}")

    return jsonify({"success": True, "payment_id": payment_id})


# ── JOB SWITCH TAX CALCULATOR ────────────────────────────────
# Same pattern as passbook/family-passbook: the free calculator already runs
# entirely client-side, so the paid unlock is just the HMAC-verified full
# report (Challan 280 guide + Form 12B email draft) via window.print().
# Nothing the user typed is ever sent to this server.
JOBSWITCH_PRICE_PAISE = 9900  # Rs 99


@app.route("/api/create-jobswitch-order", methods=["POST", "OPTIONS"])
def create_jobswitch_order():
    """Matches the existing create_*_order() pattern exactly."""
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": JOBSWITCH_PRICE_PAISE,
            "currency": "INR",
            "receipt": f"jobswitch_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "razorpay_key": os.environ.get("RAZORPAY_KEY_ID")
        })
    except Exception as e:
        print(f"create-jobswitch-order error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/verify-jobswitch-payment", methods=["POST", "OPTIONS"])
def verify_jobswitch_payment():
    """
    Matches the existing verify_*_payment() HMAC pattern exactly. No PDF is
    generated here and no calculator input is ever sent to the server — once
    the signature checks out, the frontend unlocks window.print() itself.
    """
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")

    if not all([order_id, payment_id, signature]):
        return jsonify({"success": False, "error": "Missing required fields."}), 400

    body = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    if expected != signature:
        return jsonify({"success": False, "error": "Payment verification failed."}), 400

    print(f"[jobswitch] paid unlock | payment_id={payment_id}")

    return jsonify({"success": True, "payment_id": payment_id})


# ── PF CLAIM REJECTION DECODER ───────────────────────────────
# Upgraded from a pure client-side static lookup to a paid, Claude-generated
# CA-grade resolution report personalised to the user's specific case
# details. Payment is verified with the same HMAC pattern used everywhere
# else on the site; a promo/bypass code is also accepted so the flow can be
# tested end-to-end without a real charge (see PROMO_BYPASS_CODE below).
PFDECODER_PRICE_PAISE = 9900  # Rs 99

# Testing bypass: set PROMO_BYPASS_CODE in Railway's env vars to override
# this default once you're done testing. Any tool using this helper accepts
# this code in place of real Razorpay payment fields.
PROMO_BYPASS_CODE = os.environ.get("PROMO_BYPASS_CODE", "SALARYBIT-TEST")

PFDECODER_REMARK_LABELS = {
    "name_mismatch": "Name/details mismatch across employer, Aadhaar or EPFO records",
    "inactive_uan": "UAN inactive or not recognised / possible duplicate UAN",
    "bank_details": "Bank account details could not be verified (penny-drop failure)",
    "kyc_aadhaar": "Aadhaar not linked / e-KYC pending employer approval",
    "service_period": "Minimum service period / eligibility window not met (Form 10C / 19 / 31)",
    "employer_not_verified": "Claim pending the last employer's digital approval",
    "insufficient_balance": "Claimed amount exceeds the actual EPF passbook balance",
    "dues_payable": "Outstanding employer dues / contribution gap flagged by EPFO",
    "signature_mismatch": "Signature on the physical claim form does not match records",
    "form_not_submitted": "Signed claim printout not submitted within the 15-day window",
    "certificate_missing": "Required certificate or supporting document not attached",
    "other": "Remark not in the standard list — see the user's own description",
}

PFDECODER_SYSTEM_PROMPT = """You are a senior EPFO compliance consultant preparing a formal case
resolution report for a paying client whose EPF (Employees' Provident Fund) withdrawal, transfer,
or pension claim was rejected. The client has paid Rs 99 for a CA-grade, personalised report —
write with the precision, structure and professional tone of a report a chartered accountant or
compliance consultant would hand a client, not a generic FAQ answer.

You will be given: the claim type, the closest-matching standard rejection category, any exact
remark text the client pasted from the EPFO portal, the claimed amount if given, the client's name
if given, and any free-text context they added about their situation.

Ground your analysis in these known EPFO rejection categories and their standard resolution paths
(use this as your factual base — do not contradict it, but DO personalise the specific steps,
likely timeline, and framing to what the client actually described):
""" + json.dumps(PFDECODER_REMARK_LABELS, indent=2) + """

Rules:
- Do NOT invent specific EPFO circular numbers, section numbers, or statistics you are not certain
  of. Reference well-known, standard mechanisms plainly (UAN portal KYC, EPFiGMS grievance portal,
  Form 19/10C/31, regional EPFO office, employer digital approval) rather than fabricating citations.
- If the client's free-text context reveals something that changes the diagnosis (e.g. they mention
  multiple employers, a closed company, an amount that looks CTC-based rather than passbook-based),
  address that directly and adjust the guidance — this personalisation is the entire value of the
  paid report over the free static explanation.
- Be direct and specific about what to click, whom to contact, and what to check next — a client
  paying for this expects an action plan, not general reassurance.
- This is educational/procedural guidance, not legal advice or a guarantee of outcome — say so once,
  briefly, in the disclaimer field only; do not hedge throughout the report.

Respond ONLY with a single JSON object (no markdown fences, no preamble), matching this exact shape:

{
  "case_summary": "2-3 sentence professional restatement of the client's specific case",
  "root_cause": "1-2 paragraph plain-English explanation of why this was rejected, personalised using whatever the client told you",
  "resolution_steps": [
    {"step": "short imperative title", "detail": "1-3 sentences of specific instruction"}
  ],
  "documents_required": ["specific document or evidence needed, if any — empty list if none"],
  "timeline_estimate": "concrete, realistic estimate in days/weeks",
  "reapply_guidance": "exactly when and how to reapply or follow up",
  "risk_flags": ["anything about THIS specific case worth flagging — empty list if nothing stands out"],
  "escalation_path": "where to escalate if the standard steps don't resolve it within the estimated timeline (EPFiGMS, regional PF Commissioner, EPFO helpline 1800-118-005)",
  "disclaimer": "one sentence noting this is procedural guidance based on standard EPFO practice, not a guarantee, and not a substitute for direct confirmation from EPFO/a CA in unusual cases"
}"""


def _call_claude_pfdecoder_report(case):
    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    if not claude_key:
        raise RuntimeError("Server not configured. Missing ANTHROPIC_API_KEY.")

    user_content = json.dumps(case, indent=2)

    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 3000,
        "system": PFDECODER_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_content}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": claude_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=90) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    raw = "".join(
        block.get("text", "") for block in result.get("content", []) if block.get("type") == "text"
    ).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


@app.route("/api/create-pfdecoder-order", methods=["POST", "OPTIONS"])
def create_pfdecoder_order():
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": PFDECODER_PRICE_PAISE,
            "currency": "INR",
            "receipt": f"pfdecoder_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "razorpay_key": os.environ.get("RAZORPAY_KEY_ID")
        })
    except Exception as e:
        print(f"create-pfdecoder-order error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/verify-pfdecoder-payment", methods=["POST", "OPTIONS"])
def verify_pfdecoder_payment():
    """Verifies payment (or a promo bypass code for testing), then runs the
    Claude-generated CA-grade report on the client's case details and
    returns it in the same response — same pattern as verify-payslip-payment."""
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}

    promo_code = (data.get("promo_code") or "").strip()
    payment_id = None

    if promo_code and promo_code == PROMO_BYPASS_CODE:
        payment_id = f"promo_{os.urandom(4).hex()}"
        print(f"[pfdecoder] PROMO bypass unlock | code used")
    else:
        order_id = data.get("razorpay_order_id")
        payment_id = data.get("razorpay_payment_id")
        signature = data.get("razorpay_signature")

        if not all([order_id, payment_id, signature]):
            return jsonify({"success": False, "error": "Missing required fields."}), 400

        body = f"{order_id}|{payment_id}"
        expected = hmac.new(
            os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()
        if expected != signature:
            return jsonify({"success": False, "error": "Payment verification failed."}), 400

        print(f"[pfdecoder] paid unlock | payment_id={payment_id}")

    case = {
        "claim_type": data.get("claim_type") or "Not specified",
        "rejection_category": PFDECODER_REMARK_LABELS.get(
            data.get("remark_key"), data.get("remark_key") or "Not specified"
        ),
        "exact_remark_text": data.get("remark_text") or None,
        "claimed_amount_inr": data.get("claimed_amount") or None,
        "client_name": data.get("client_name") or None,
        "additional_context": data.get("extra_context") or None,
    }

    try:
        report = _call_claude_pfdecoder_report(case)
    except Exception as e:
        print(f"pfdecoder report generation error: {type(e).__name__}: {e}")
        return jsonify({
            "success": True,
            "payment_id": payment_id,
            "error": "Payment succeeded, but report generation failed. You will not be "
                     "charged again — contact support with this payment ID and we'll get "
                     "your report to you directly."
        })

    return jsonify({"success": True, "payment_id": payment_id, "report": report})


# ── PAN CORRECTION NAVIGATOR ─────────────────────────────────
# Upgraded from a pure client-side wizard to a paid, Claude-generated
# CA-grade resolution report. The free wizard stays as the instant
# directional read; the paid report is personalised to the user's exact
# situation and — critically — correctly separates two very different
# problems that people conflate: a simple detail correction (fast, online,
# NSDL/Protean or UTIITSL) versus holding a duplicate PAN (slow, offline,
# routed through the jurisdictional Assessing Officer, not a correction
# form at all).
PANCORRECTION_PRICE_PAISE = 9900  # Rs 99

PANCORRECTION_SYSTEM_PROMPT = """You are a senior tax consultant (CA-level) preparing a formal case
resolution report for a paying client dealing with a PAN card problem in India. The client has paid
Rs 99 for a personalised report — write with the precision and structure of a report a chartered
accountant would hand a client, not a generic FAQ answer.

You will be given: the issue category the free tool diagnosed (name mismatch severity, duplicate PAN
suspicion, which agency issued the PAN if known), the names as they appear on PAN/Aadhaar/bank
records, and free-text context the client added about their specific situation. The client has been
told NOT to share full PAN or Aadhaar numbers — do not ask for them or assume you have been given
them; work from the situation described.

CRITICAL — get this distinction right, it is the main value of this report over generic advice:

1. SIMPLE DETAIL CORRECTION (name spelling, DOB, address, photo/signature, minor name mismatch that
   Aadhaar-OTP linking can absorb): this is fast and handled entirely online via the PAN-issuing
   agency's own correction portal (Protean/NSDL "Changes or Correction in PAN Data", or UTIITSL "PAN
   Card Change Request"). Typical turnaround is 15–45 days. This is a routine data-correction filing.

2. DUPLICATE / MULTIPLE PAN (holding two PAN numbers, even if one was issued in error and never used):
   this is NOT a correction-form issue. It is a compliance issue under Section 139A(7) of the Income
   Tax Act (penalty under Section 272B for holding more than one PAN). It CANNOT be resolved through
   the NSDL/UTIITSL online correction portal — those portals only edit details on a single PAN, they
   do not surrender/close a duplicate one. The actual real-world process is:
   - Identify the client's jurisdictional Assessing Officer (AO) via "Know Your AO" on the Income Tax
     e-filing portal (incometax.gov.in).
   - Decide which PAN to KEEP — normally the one with actual transaction/filing/bank-linkage history —
     and prepare a written surrender request for the OTHER one, addressed to that AO, enclosing copies
     of both PAN cards.
   - If the duplicate card was never received, is lost, or the client doesn't have it: file a police
     complaint (FIR or a local online police complaint) for the lost PAN card first. That complaint
     record substitutes for the physical card copy when requesting surrender.
   - The AO will check the PAN proposed for surrender for any transaction history (bank accounts, ITR
     filings, TDS entries linked to it). It can only be closed if it shows NO transactions. If it does
     show transactions, that history has to be explained/reconciled first, which adds significant time.
   - This is a manual, offline, AO-driven process. It commonly takes many months, and in unresponsive
     jurisdictions has taken multiple years in real cases — set expectations honestly, do not
     understate this.
   - Even after the AO confirms surrender/closure (sometimes only as a local printout/letter), this
     status does NOT automatically propagate to banks, NPS, DigiLocker, or other systems that still
     have the old PAN or the old name on file. The client must proactively submit the AO's closure
     confirmation to each of those systems and follow up — nothing updates itself.
   - A related, separate symptom worth flagging if the client mentions it: even after a corrected PAN
     is issued, older linked records (e.g. NPS, an old bank KYC entry) can keep showing the pre-
     correction name until the client manually re-submits KYC/updates there too — this is a common,
     frustrating follow-on step people don't expect.

Rules:
- Do not blend the two paths above. If the client's situation is a duplicate PAN, do not tell them to
  use the NSDL/UTIITSL correction portal for that — direct them to the AO route. If it is a simple
  correction, do not send them down the AO/surrender path.
- Do not invent specific processing-time guarantees; give realistic ranges and say they vary by
  jurisdiction and AO responsiveness.
- Be direct and specific about what to do next — a client paying for this expects an action plan.
- This is educational/procedural guidance, not legal advice — say so once, briefly, in the disclaimer
  field only.

Respond ONLY with a single JSON object (no markdown fences, no preamble), matching this exact shape:

{
  "case_summary": "2-3 sentence professional restatement of the client's specific case",
  "root_cause": "1-2 paragraph plain-English explanation of what's actually going on and WHY, personalised using whatever the client told you",
  "resolution_steps": [
    {"step": "short imperative title", "detail": "1-3 sentences of specific instruction"}
  ],
  "documents_required": ["specific document or evidence needed, if any — empty list if none"],
  "timeline_estimate": "concrete, realistic estimate — for duplicate PAN cases, be honest that this can take months and set expectations accordingly",
  "reapply_guidance": "what to do once the correction/surrender is confirmed — including any propagation follow-up needed at banks/NPS/other KYC systems",
  "risk_flags": ["anything about THIS specific case worth flagging — empty list if nothing stands out"],
  "escalation_path": "where to escalate if standard steps stall (CPGRAMS grievance portal, Income Tax e-Nivaran, or the AO's superior officer for duplicate-PAN cases stuck beyond a reasonable time)",
  "disclaimer": "one sentence noting this is procedural guidance based on standard Income Tax Department practice, not a guarantee, and not a substitute for direct confirmation from a CA or the AO in unusual cases"
}"""


def _call_claude_pancorrection_report(case):
    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    if not claude_key:
        raise RuntimeError("Server not configured. Missing ANTHROPIC_API_KEY.")

    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 3000,
        "system": PANCORRECTION_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": json.dumps(case, indent=2)}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": claude_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=90) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    raw = "".join(
        block.get("text", "") for block in result.get("content", []) if block.get("type") == "text"
    ).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


@app.route("/api/create-pancorrection-order", methods=["POST", "OPTIONS"])
def create_pancorrection_order():
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": PANCORRECTION_PRICE_PAISE,
            "currency": "INR",
            "receipt": f"pancorrection_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "razorpay_key": os.environ.get("RAZORPAY_KEY_ID")
        })
    except Exception as e:
        print(f"create-pancorrection-order error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/verify-pancorrection-payment", methods=["POST", "OPTIONS"])
def verify_pancorrection_payment():
    """Verifies payment (or a promo bypass code), then runs the Claude-
    generated CA-grade report on the client's case and returns it."""
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}

    promo_code = (data.get("promo_code") or "").strip()
    payment_id = None

    if promo_code and promo_code == PROMO_BYPASS_CODE:
        payment_id = f"promo_{os.urandom(4).hex()}"
        print(f"[pancorrection] PROMO bypass unlock | code used")
    else:
        order_id = data.get("razorpay_order_id")
        payment_id = data.get("razorpay_payment_id")
        signature = data.get("razorpay_signature")

        if not all([order_id, payment_id, signature]):
            return jsonify({"success": False, "error": "Missing required fields."}), 400

        body = f"{order_id}|{payment_id}"
        expected = hmac.new(
            os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()
        if expected != signature:
            return jsonify({"success": False, "error": "Payment verification failed."}), 400

        print(f"[pancorrection] paid unlock | payment_id={payment_id}")

    case = {
        "issue_category": data.get("issue_category") or "Not specified",
        "duplicate_pan_suspected": data.get("duplicate_pan_suspected") or "no",
        "pan_issuer": data.get("pan_issuer") or "Not specified",
        "name_on_pan": data.get("name_on_pan") or None,
        "name_on_aadhaar": data.get("name_on_aadhaar") or None,
        "name_on_bank": data.get("name_on_bank") or None,
        "duplicate_card_status": data.get("duplicate_card_status") or None,
        "client_name": data.get("client_name") or None,
        "additional_context": data.get("extra_context") or None,
    }

    try:
        report = _call_claude_pancorrection_report(case)
    except Exception as e:
        print(f"pancorrection report generation error: {type(e).__name__}: {e}")
        return jsonify({
            "success": True,
            "payment_id": payment_id,
            "error": "Payment succeeded, but report generation failed. You will not be "
                     "charged again — contact support with this payment ID and we'll get "
                     "your report to you directly."
        })

    return jsonify({"success": True, "payment_id": payment_id, "report": report})


# ── SUPERANNUATION FUND NAVIGATOR ────────────────────────────
# Pure client-side decision tree. Same paid-unlock pattern — nothing
# selected is ever sent to this server.
SUPERANNUATION_PRICE_PAISE = 9900  # Rs 99


@app.route("/api/create-superannuation-order", methods=["POST", "OPTIONS"])
def create_superannuation_order():
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": SUPERANNUATION_PRICE_PAISE,
            "currency": "INR",
            "receipt": f"superann_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "razorpay_key": os.environ.get("RAZORPAY_KEY_ID")
        })
    except Exception as e:
        print(f"create-superannuation-order error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/verify-superannuation-payment", methods=["POST", "OPTIONS"])
def verify_superannuation_payment():
    """Matches the existing verify_*_payment() HMAC pattern exactly."""
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")

    if not all([order_id, payment_id, signature]):
        return jsonify({"success": False, "error": "Missing required fields."}), 400

    body = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    if expected != signature:
        return jsonify({"success": False, "error": "Payment verification failed."}), 400

    print(f"[superannuation] paid unlock | payment_id={payment_id}")
    return jsonify({"success": True, "payment_id": payment_id})


# ── RELIEVING LETTER ESCALATION KIT ──────────────────────────
# Pure client-side letter generator. Same paid-unlock pattern — nothing
# typed (name, company, days) is ever sent to this server.
RELIEVINGLETTER_PRICE_PAISE = 9900  # Rs 99


@app.route("/api/create-relievingletter-order", methods=["POST", "OPTIONS"])
def create_relievingletter_order():
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": RELIEVINGLETTER_PRICE_PAISE,
            "currency": "INR",
            "receipt": f"relieveletter_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "razorpay_key": os.environ.get("RAZORPAY_KEY_ID")
        })
    except Exception as e:
        print(f"create-relievingletter-order error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/verify-relievingletter-payment", methods=["POST", "OPTIONS"])
def verify_relievingletter_payment():
    """Matches the existing verify_*_payment() HMAC pattern exactly."""
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")

    if not all([order_id, payment_id, signature]):
        return jsonify({"success": False, "error": "Missing required fields."}), 400

    body = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    if expected != signature:
        return jsonify({"success": False, "error": "Payment verification failed."}), 400

    print(f"[relievingletter] paid unlock | payment_id={payment_id}")
    return jsonify({"success": True, "payment_id": payment_id})


# ── PAYSLIP COMPARER / PAY STRUCTURE SIMULATOR ───────────────
# Users upload 2-4 months of payslips. Free step extracts text + a
# best-effort take-home teaser (regex, no Claude call — payslip layouts
# vary too much across employers to trust regex for anything beyond a
# quick headline number, so this degrades gracefully to a generic
# message rather than a wrong one). Paid step (₹99) sends the raw text
# of every payslip to Claude, which structures, compares, and explains
# what changed and why — including New Labour Code wage-restructuring
# detection, backdated-arrears math, a plain-language "why your amount
# changed" explanation for non-finance users, a New Tax Regime NPS
# 80CCD(2) tax-saving tip, and a next-month take-home estimate.
PAYSLIP_COMPARE_PRICE_PAISE = 9900  # Rs 99

# In-memory cache: scan_id -> {"texts": [...raw payslip text...], "ts": epoch}
# Mirrors _SUBSCRIPTION_SCAN_CACHE — holds extracted text between the free
# upload and the paid Claude call so payment doesn't require re-uploading.
_PAYSLIP_SCAN_CACHE = {}
_PAYSLIP_CACHE_TTL = 1800  # 30 minutes


def _payslip_cache_put(texts):
    _payslip_cache_gc()
    scan_id = uuid.uuid4().hex
    _PAYSLIP_SCAN_CACHE[scan_id] = {"texts": texts, "ts": _time.time()}
    return scan_id


def _payslip_cache_pop(scan_id):
    entry = _PAYSLIP_SCAN_CACHE.pop(scan_id, None)
    if not entry:
        return None
    if _time.time() - entry["ts"] > _PAYSLIP_CACHE_TTL:
        return None
    return entry["texts"]


def _payslip_cache_peek(scan_id):
    """Like _payslip_cache_pop but does NOT remove the entry. Used so a failed
    Claude call doesn't destroy the payslip text — only a successful report
    consumes the cache entry."""
    entry = _PAYSLIP_SCAN_CACHE.get(scan_id)
    if not entry:
        return None
    if _time.time() - entry["ts"] > _PAYSLIP_CACHE_TTL:
        return None
    return entry["texts"]


def _payslip_cache_gc():
    now = _time.time()
    expired = [k for k, v in _PAYSLIP_SCAN_CACHE.items() if now - v["ts"] > _PAYSLIP_CACHE_TTL]
    for k in expired:
        _PAYSLIP_SCAN_CACHE.pop(k, None)


def _extract_take_home_teaser(text):
    """Best-effort only. Payslip layouts vary a lot across employers, so
    this looks for a 'Take Home Pay' label followed by a rupee figure
    within a short window of text, and returns None (not a guess) if it
    can't find one confidently. The paid Claude step does the real,
    format-agnostic parsing."""
    m = re.search(r'Take\s*Home\s*Pay[^\d₹]{0,15}₹?\s*([\d,]+\.\d{1,2})', text, re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


@app.route('/payslip-comparer', methods=['GET'])
def payslip_comparer_page():
    """Serves the tool itself, same static-HTML-next-to-server pattern as
    subscription-leak-finder.html and patience-passbook.html."""
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'payslip-comparer.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        content_html = f.read()
    return Response(content_html, mimetype='text/html')


@app.route('/api/payslip-scan', methods=['POST', 'OPTIONS'])
def payslip_scan():
    """Free step: extract text from 2-4 uploaded payslip PDFs, cache it,
    and return a lightweight teaser (file count + best-effort take-home
    numbers if regex finds them). No Claude call here — see docstring
    above the price constant for why."""
    if request.method == "OPTIONS":
        return "", 200

    files = request.files.getlist('payslips')
    if not files:
        return jsonify({"error": "Upload at least 2 payslip PDFs to compare (up to 4)."}), 400
    if len(files) < 2:
        return jsonify({"error": "Upload at least 2 payslips so there's something to compare."}), 400
    if len(files) > 4:
        return jsonify({"error": "Max 4 payslips at a time — pick the ones you most want compared."}), 400

    texts = []
    take_home_values = []
    for f in files:
        if not f.filename.lower().endswith('.pdf'):
            return jsonify({"error": f"{f.filename} is not a PDF."}), 400
        try:
            with pdfplumber.open(f) as pdf:
                pages_text = [(p.extract_text() or "") for p in pdf.pages]
            text = "\n".join(pages_text).strip()
        except Exception as e:
            return jsonify({"error": f"Could not read {f.filename}: {e}"}), 400
        if not text:
            return jsonify({
                "error": f"{f.filename} looks like a scanned image with no extractable text. "
                         f"Please upload the original digital payslip PDF, not a scan or photo."
            }), 400
        texts.append(text)
        take_home_values.append(_extract_take_home_teaser(text))

    scan_id = _payslip_cache_put(texts)
    teaser = {"scan_id": scan_id, "file_count": len(texts)}

    known = [v for v in take_home_values if v is not None]
    if len(known) >= 2:
        teaser["take_home_delta"] = round(known[-1] - known[0], 2)
        teaser["first_take_home"] = round(known[0], 2)
        teaser["last_take_home"] = round(known[-1], 2)

    return jsonify(teaser)


@app.route('/api/create-payslip-order', methods=['POST', 'OPTIONS'])
def create_payslip_order():
    """Matches the existing create_*_order() pattern exactly."""
    if request.method == "OPTIONS":
        return "", 200
    try:
        order = rzp.order.create({
            "amount": PAYSLIP_COMPARE_PRICE_PAISE,
            "currency": "INR",
            "receipt": f"payslipcmp_{os.urandom(4).hex()}",
        })
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "razorpay_key": os.environ.get("RAZORPAY_KEY_ID")
        })
    except Exception as e:
        print(f"create-payslip-order error: {e}")
        return jsonify({"error": str(e)}), 500


PAYSLIP_ANALYSIS_SYSTEM_PROMPT = """You are a meticulous Indian payroll and personal-finance \
analyst writing for SalaryBit, a platform for Indian salaried professionals. You'll receive the \
raw extracted text of 2-4 consecutive monthly payslips for one person, in upload order (assume \
chronological, oldest first, unless the payslip text itself shows dates proving otherwise).

The single most important thing you produce is "why_amount_changed": a warm, plain-English \
paragraph (4-6 sentences) explaining, for someone with ZERO finance background, exactly why \
their take-home pay went up or down. Lead with the one biggest cause. No jargon without \
immediately explaining it in parentheses. This is the one section every paying customer reads \
first — it has to be completely correct and completely clear, or the product fails at its one job.

Your job:
1. Parse each payslip into structured line items (earnings, deductions, take-home, PF, income
   tax, loan recovery, Form 16 / tax-summary figures if present).
2. Compare month over month: every component that appeared, disappeared, increased, or
   decreased, with exact rupee deltas and percentage change.
3. Explain WHY, considering real causes: annual increment/promotion, bonus/variable pay timing,
   India's New Labour Codes wage restructuring (Code on Wages requires Basic + Dearness
   Allowance to be at least 50% of total remuneration — many employers restructured Basic/HRA/
   Special Allowance during 2025-2026, often paying backdated arrears as a lump sum), backdated
   arrears (look for "BF"/"Brought Forward"/"Arrears" lines — if a delta is roughly N times a
   recurring monthly delta, that's N months of arrears), PF changes (PF is a % of Basic),
   income-tax/TDS swings (can spike temporarily from one-time arrears inflating that month's
   projected annual income, then normalize), loan disbursement/payoff, equity/RSU events
   (one-time, not recurring pay), professional tax/ESI changes, LOP (loss-of-pay) days.
4. Flag anything that looks like an error or worth a question to HR/payroll.
5. Wage-code note: what % of total earnings is Basic (+DA if shown)? Trending toward or away
   from the 50% floor?
6. NPS tax-saving tip for the New Tax Regime (assume New Tax Regime unless the payslip text
   explicitly says "Tax Regime: Old"): under Section 80CCD(2), an EMPLOYER's contribution to the
   employee's NPS account is deductible even under the new regime, up to 14% of Basic + DA — this
   applies to private-sector employees too (since FY2025-26), and does not reduce the employer's
   CTC cost, just reclassifies part of it. The employee's OWN NPS contribution under 80CCD(1B)
   (₹50,000 extra) is NOT deductible under the new regime — old regime only; do not recommend it
   as a new-regime tax-saver. If the payslip shows no employer NPS line item, explain this as an
   actionable opportunity: ask HR to route part of CTC into employer NPS under 80CCD(2), and
   estimate the annual tax saving using their approximate marginal slab rate implied by the
   Form-16/tax-summary figures if present (New Tax Regime FY2026-27 slabs, unchanged from
   FY2025-26 per Budget 2026: 0-4L nil, 4-8L 5%, 8-12L 10%, 12-16L 15%, 16-20L 20%, 20-24L 25%,
   above 24L 30%, with a rebate that makes total taxable income up to ~₹12L effectively tax-free).
   If employer NPS is already present, just confirm it's working in their favour and estimate the
   saving from what's already being contributed.
7. Estimate NEXT month's take-home: assume the most recent month's *recurring* components repeat
   with no further one-time arrears/equity/bonus, adjust income tax down if the most recent
   month's TDS looks arrears-inflated (use the Form 16 "tax deducted so far" vs "tax payable and
   surcharge" figures, spread the remainder over the remaining months of the financial year
   April-March if visible), and account for any loan recovery that is scheduled to continue or
   finish based on the loan balance shown.

Do NOT invent figures. If a payslip's text is garbled or a field unclear, say so plainly instead
of guessing. This is educational analysis, not a substitute for a CA or the employer's HR/payroll
team — say so briefly where relevant, without hedging so much it undermines the confident,
customer-facing "why_amount_changed" explanation people are paying for.

Respond ONLY with a single JSON object (no markdown fences, no preamble), matching this shape:

{
  "why_amount_changed": "the 4-6 sentence plain-English paragraph described above",
  "months": [
    {"label": "June 2026", "take_home": 153105.00, "total_earnings": 180043.03,
     "total_deductions": 26938.00, "basic": 60896.50, "basic_pct_of_earnings": 33.8}
  ],
  "headline_summary": "1-2 sentence summary of the single biggest story across these payslips.",
  "changes": [
    {"component": "Basic Salary", "type": "increase|decrease|new|removed",
     "from_month": "June 2026", "from_value": 60896.50,
     "to_month": "July 2026", "to_value": 71495.03,
     "delta": 10598.53, "delta_pct": 17.4, "likely_reason": "plain-English explanation"}
  ],
  "arrears_detected": [
    {"line_item": "BF Basic Arrears", "amount": 31795.59,
     "explanation": "= 3 x the recurring Basic increase of 10598.53, i.e. 3 months of backdated arrears"}
  ],
  "flags_for_hr": ["anything worth questioning, or empty list"],
  "wage_code_note": "1-2 sentences on Basic vs the 50% threshold and whether this looks like labour-code-driven restructuring, or null",
  "nps_tax_saving_tip": {
    "has_employer_nps": true,
    "estimated_annual_saving": 20800,
    "explanation": "1-3 sentences, concrete and actionable, following the 80CCD(2) rules above"
  },
  "next_month_estimate": {
    "label": "August 2026",
    "estimated_take_home_low": 134000, "estimated_take_home_high": 137000,
    "basis": "1-2 sentence explanation of the estimate"
  }
}

If only ONE usable payslip is present, instead return:
{"single_payslip": true, "summary": "...", "why_amount_changed": null, "breakdown": {...}, "flags_for_hr": [...]}
"""


def _call_claude_payslip_analysis(payslip_texts):
    claude_key = os.environ.get("ANTHROPIC_API_KEY")
    if not claude_key:
        raise RuntimeError("Server not configured. Missing ANTHROPIC_API_KEY.")

    numbered = "\n\n".join(
        f"===== PAYSLIP {i+1} of {len(payslip_texts)} =====\n{t}"
        for i, t in enumerate(payslip_texts)
    )

    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "system": PAYSLIP_ANALYSIS_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": numbered}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": claude_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )

    # 8000-token structured analyses across up to 4 payslips can legitimately
    # take longer than 90s. One attempt, generous timeout, no stacked retry —
    # retrying the same slow call would risk exceeding gunicorn's worker
    # timeout (Procfile) and getting SIGKILLed instead of failing cleanly.
    # NOTE: bump gunicorn's --timeout in the Procfile to stay comfortably
    # above this value (see accompanying Procfile change).
    with urllib.request.urlopen(req, timeout=170) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    raw = "".join(
        block.get("text", "") for block in result.get("content", []) if block.get("type") == "text"
    ).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


@app.route('/api/verify-payslip-payment', methods=['POST', 'OPTIONS'])
def verify_payslip_payment():
    """Matches the existing verify_*_payment() HMAC pattern exactly. On
    success, runs the (single) Claude analysis call on the cached payslip
    text and returns the full report in the same response."""
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")
    scan_id = data.get("scan_id")

    if not all([order_id, payment_id, signature]):
        return jsonify({"success": False, "error": "Missing required fields."}), 400

    body = f"{order_id}|{payment_id}"
    expected = hmac.new(
        os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    if expected != signature:
        return jsonify({"success": False, "error": "Payment verification failed."}), 400

    print(f"[payslip-comparer] paid unlock | payment_id={payment_id}")

    if not scan_id:
        return jsonify({"success": True})

    texts = _payslip_cache_peek(scan_id)
    if texts is None:
        return jsonify({
            "success": True,
            "error": "Your session expired. Payment succeeded, but please re-upload your "
                     "payslips (you will not be charged again — contact support with this "
                     "payment ID if needed) to view the report.",
            "payment_id": payment_id
        })

    try:
        analysis = _call_claude_payslip_analysis(texts)
    except Exception as e:
        print(f"payslip analysis error: {type(e).__name__}: {e}")
        return jsonify({
            "success": True,
            "error": "Payment succeeded but the report could not be generated right now. "
                     "Please contact support with this payment ID and we'll generate it for you.",
            "payment_id": payment_id
        })

    _payslip_cache_pop(scan_id)  # only consume the cache once the report actually succeeded

    return jsonify({"success": True, "analysis": analysis, "payment_id": payment_id})


@app.route('/api/payslip-report-pdf', methods=['POST', 'OPTIONS'])
def payslip_report_pdf():
    """Regenerates the paid report as a downloadable PDF. Requires the
    already-verified analysis JSON to be POSTed back (no server-side
    payment re-check here since this only runs after verify-payslip-payment
    has already handed the analysis to the browser — same trust boundary
    as every other client-rendered paid report on this site)."""
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(silent=True) or {}
    analysis = data.get("analysis")
    if not analysis:
        return jsonify({"error": "No report data provided."}), 400

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib import colors as rl_colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except ImportError:
        return jsonify({"error": "PDF generation not available on the server."}), 500

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=20 * mm,
                             leftMargin=18 * mm, rightMargin=18 * mm)
    styles = getSampleStyleSheet()
    brand_style = ParagraphStyle("BrandX", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold",
                                  textColor=rl_colors.HexColor("#00a656"), spaceAfter=2)
    title_style = ParagraphStyle("TitleX", parent=styles["Title"], fontSize=20,
                                  textColor=rl_colors.HexColor("#0b0e14"), spaceBefore=0, spaceAfter=2)
    meta_style = ParagraphStyle("MetaX", parent=styles["BodyText"], fontSize=9, textColor=rl_colors.HexColor("#6b7280"))
    h2 = ParagraphStyle("H2X", parent=styles["Heading2"], fontSize=13, textColor=rl_colors.HexColor("#00a656"),
                         spaceBefore=16, spaceAfter=4)
    body = styles["BodyText"]
    small = ParagraphStyle("Small", parent=styles["BodyText"], fontSize=8.5, textColor=rl_colors.grey)
    summary_style = ParagraphStyle("SummaryX", parent=styles["BodyText"], fontSize=12, fontName="Helvetica-Bold",
                                    textColor=rl_colors.HexColor("#0b0e14"), leading=16)
    disclaimer_style = ParagraphStyle("DisclaimerX", parent=styles["BodyText"], fontSize=8, textColor=rl_colors.grey,
                                       leading=11)

    report_id = f"SB-PC-{datetime.now().strftime('%Y%m%d')}-{os.urandom(3).hex().upper()}"

    from reportlab.platypus.flowables import HRFlowable
    story = [
        Paragraph("SALARYBIT", brand_style),
        Paragraph("Payslip Comparison Report", title_style),
        HRFlowable(width="100%", thickness=1.4, color=rl_colors.HexColor("#00a656"), spaceAfter=6),
        Paragraph(
            f"Report ID: {report_id} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Generated: {datetime.now().strftime('%d %b %Y, %I:%M %p')} IST &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"AI-Assisted Payroll Analysis",
            meta_style
        ),
        Spacer(1, 6 * mm),
    ]

    headline = analysis.get("headline_summary")
    if headline and not analysis.get("single_payslip"):
        story.append(Table(
            [[Paragraph(headline, summary_style)]],
            colWidths=[doc.width],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), rl_colors.HexColor("#eafff3")),
                ("BOX", (0, 0), (-1, -1), 0.75, rl_colors.HexColor("#00a656")),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ])
        ))
        story.append(Spacer(1, 6 * mm))

    section_num = [0]
    def numbered_h2(text):
        section_num[0] += 1
        return Paragraph(f"{section_num[0]}. {text}", h2)

    if analysis.get("single_payslip"):
        story.append(numbered_h2("Summary"))
        story.append(Paragraph(analysis.get("summary", ""), body))
    else:
        if analysis.get("why_amount_changed"):
            story.append(numbered_h2("Why Your Take-Home Changed"))
            story.append(Paragraph(analysis["why_amount_changed"], body))

        months = analysis.get("months", [])
        if months:
            story.append(numbered_h2("Month-by-Month Snapshot"))
            rows = [["Month", "Total Earnings", "Total Deductions", "Take Home", "Basic", "Basic % of Earnings"]]
            for m in months:
                rows.append([
                    m.get("label", ""), f"Rs {(m.get('total_earnings') or 0):,.2f}",
                    f"Rs {(m.get('total_deductions') or 0):,.2f}", f"Rs {(m.get('take_home') or 0):,.2f}",
                    f"Rs {(m.get('basic') or 0):,.2f}", f"{(m.get('basic_pct_of_earnings') or 0):.1f}%",
                ])
            t = Table(rows, repeatRows=1, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#00a656")),
                ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#f8fafc")]),
            ]))
            story.append(t)

        changes = analysis.get("changes", [])
        if changes:
            story.append(numbered_h2("What Changed & Why"))
            for c in changes:
                line = (f"<b>{c.get('component')}</b> ({c.get('type')}): {c.get('from_month','')} "
                        f"Rs {(c.get('from_value') or 0):,.2f} to {c.get('to_month','')} "
                        f"Rs {(c.get('to_value') or 0):,.2f} (Delta Rs {(c.get('delta') or 0):,.2f}, {(c.get('delta_pct') or 0):.1f}%)")
                story.append(Paragraph(line, body))
                story.append(Paragraph(c.get("likely_reason", ""), small))
                story.append(Spacer(1, 3 * mm))

        arrears = analysis.get("arrears_detected", [])
        if arrears:
            story.append(numbered_h2("Arrears / Backdated Payments Detected"))
            for a in arrears:
                story.append(Paragraph(f"<b>{a.get('line_item')}</b>: Rs {(a.get('amount') or 0):,.2f}", body))
                story.append(Paragraph(a.get("explanation", ""), small))
                story.append(Spacer(1, 2 * mm))

        if analysis.get("wage_code_note"):
            story.append(numbered_h2("New Labour Code / Wage Structure Note"))
            story.append(Paragraph(analysis["wage_code_note"], body))

        nps = analysis.get("nps_tax_saving_tip")
        if nps:
            story.append(numbered_h2("NPS Tax-Saving Tip (New Tax Regime)"))
            if nps.get("estimated_annual_saving"):
                story.append(Paragraph(f"Estimated annual tax saving: Rs {nps['estimated_annual_saving']:,.0f}", body))
            story.append(Paragraph(nps.get("explanation", ""), small))

        flags = analysis.get("flags_for_hr", [])
        if flags:
            story.append(numbered_h2("Worth Raising With HR/Payroll"))
            for fl in flags:
                story.append(Paragraph(f"- {fl}", body))

        nxt = analysis.get("next_month_estimate")
        if nxt:
            story.append(numbered_h2(f"Next Month Estimate — {nxt.get('label','')}"))
            story.append(Paragraph(
                f"Estimated take-home: Rs {(nxt.get('estimated_take_home_low') or 0):,.0f} - "
                f"Rs {(nxt.get('estimated_take_home_high') or 0):,.0f}", body))
            story.append(Paragraph(nxt.get("basis", ""), small))

    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=0.6, color=rl_colors.HexColor("#d1d5db"), spaceAfter=6))
    story.append(Paragraph(
        "<b>Disclaimer:</b> This report is an educational, AI-assisted analysis of the payslip "
        "text you uploaded. It is not a substitute for advice from a qualified Chartered "
        "Accountant, tax advisor, or your employer's HR/payroll team, and figures should be "
        "verified against your official Form 16 and payroll records before you act on them. "
        f"Report generated by SalaryBit.in on {datetime.now().strftime('%d %b %Y')}.",
        disclaimer_style))

    doc.build(story)
    buf.seek(0)
    filename = f"salarybit-payslip-report-{datetime.now().strftime('%Y%m%d')}.pdf"
    return Response(
        buf.read(), mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ── HEALTH CHECK ──────────────────────────────────────────
@app.route("/api/capture-lead", methods=["POST", "OPTIONS"])
def capture_lead():
    """
    Stores lead emails from waitlist/lead-magnet forms (e.g. the
    'Full CA Tax Breakdown PDF' waitlist on old-vs-new-tax-regime.html).

    Primary store: a Google Sheet, via a webhook URL set in the
    GOOGLE_SHEET_WEBHOOK_URL environment variable on Railway
    (see salarybit-lead-sheet-webhook.gs for the Apps Script to deploy).

    Fallback store: a local leads.jsonl file. Railway's filesystem is
    ephemeral, so this file will NOT survive a redeploy or restart —
    it only exists so a lead isn't silently lost if the Sheet webhook
    is unreachable for a moment. Set GOOGLE_SHEET_WEBHOOK_URL for the
    real, durable copy.
    """
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    source = (data.get("source") or "unknown").strip()[:100]

    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"error": "Please enter a valid email address."}), 400

    entry = {
        "email": email,
        "source": source,
        "ts": datetime.utcnow().isoformat() + "Z",
    }

    sheet_webhook_url = os.environ.get("GOOGLE_SHEET_WEBHOOK_URL", "").strip()
    sheet_ok = False
    if sheet_webhook_url:
        try:
            req = urllib.request.Request(
                sheet_webhook_url,
                data=json.dumps({"email": email, "source": source}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                resp.read()
            sheet_ok = True
        except Exception:
            sheet_ok = False  # fall through to local file below

    LEADS_FILE = os.path.join(os.path.dirname(__file__), "leads.jsonl")
    try:
        with open(LEADS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        if not sheet_ok:
            return jsonify({"error": "Could not save right now, please try again."}), 500

    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "SalaryBit API"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

