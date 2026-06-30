"""
DROP-IN ADDITIONS FOR server_railway.py

Copy these sections into your existing server_railway.py file, matching
the exact pattern you already use for the PDF Signature Validator
(EMBED_HTML string + Response()) and the QR decoder (Razorpay order
create + verify with HMAC signature).

WHERE TO ADD EACH PIECE:

1. Add these 3 imports near your other imports (top of file, after the
   existing imports around line 1-24):
"""

# ── ADD: new imports for subscription scan ──────────────────
import pdfplumber
import re
from collections import defaultdict


"""
2. Add these 3 helper functions anywhere in the "helpers" section of the
   file (e.g. right after validate_pdf_file(), around line 180), BEFORE
   the EMBED_HTML constant:
"""

# ── SUBSCRIPTION SCAN HELPERS ─────────────────────────────


def extract_transactions_from_pdf(pdf_path):
    """Generic transaction table extraction - works across bank formats."""
    all_rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
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


def identify_merchants_groq(recurring_list):
    """
    Uses your existing GROQ_API_KEY (already used in rewrite_resume()) instead
    of needing a separate Anthropic key - keeps this consistent with your stack.
    """
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key or not recurring_list:
        return [
            {**r, "identified_as": "Unknown - check manually",
             "category": "Unknown",
             "how_to_cancel": "Check NPCI UPI Autopay portal or your bank app"}
            for r in recurring_list
        ]

    txn_summaries = [
        {"narration": r["narration_sample"], "amount": r["amount"], "frequency": r["frequency"]}
        for r in recurring_list
    ]
    prompt = f"""You are helping an Indian user understand recurring bank charges auto-detected from their statement.

Rules:
- Indian context: UPI/card/ACH narrations from Indian bank statements
- "ARHA MEDIA" = Aha (Telugu/Tamil OTT app), generic "playstore" VPAs = Google Play Store app billing, "ACH D-NETFLIX" = Netflix, etc.
- If unclear, say "Unclear - check [merchant] directly" rather than guessing
- Output ONLY valid JSON array, no markdown, no preamble

Transactions:
{json.dumps(txn_summaries)}

Output format:
[{{"narration": "...", "identified_as": "...", "category": "OTT/Streaming|Telecom|Cloud/Software|Insurance|Investment SIP|Unknown|Other", "how_to_cancel": "short instruction"}}]"""

    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "temperature": 0.2,
        "max_tokens": 2048,
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
        identifications = json.loads(clean)
    except Exception as e:
        print(f"identify_merchants_groq error: {e}")
        identifications = []

    id_map = {i["narration"]: i for i in identifications}
    enriched = []
    for r in recurring_list:
        match = id_map.get(r["narration_sample"], {})
        enriched.append({
            **r,
            "identified_as": match.get("identified_as", "Unknown - check manually"),
            "category": match.get("category", "Unknown"),
            "how_to_cancel": match.get("how_to_cancel", "Check NPCI UPI Autopay or your bank app"),
        })
    return enriched


"""
3. Add these 4 ROUTES anywhere in the routes section, e.g. right after the
   validate_signature routes (around line 588), BEFORE the health check:
"""

# ── SUBSCRIPTION LEAK FINDER ──────────────────────────────

SUBSCRIPTION_SCAN_PRICE_PAISE = 4900  # Rs 49

@app.route('/subscription-leak-finder', methods=['GET'])
def subscription_leak_finder_page():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'subscription-leak-finder.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        content_html = f.read()
    return Response(content_html, mimetype='text/html')


@app.route('/api/subscription-scan', methods=['POST', 'OPTIONS'])
def subscription_scan():
    if request.method == "OPTIONS":
        return "", 200
    if 'statement' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files['statement']
    if not f.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Only PDF files are supported."}), 400

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = tmp.name
        f.save(pdf_path)

    try:
        raw_rows = extract_transactions_from_pdf(pdf_path)
        if not raw_rows:
            return jsonify({
                "error": "Could not detect a transaction table. Make sure this is a downloaded statement, not a scanned image.",
                "subscriptions": []
            })

        txns = classify_statement_rows(raw_rows)
        recurring = detect_recurring_charges(txns)

        if not recurring:
            return jsonify({"subscriptions": [], "message": "No recurring subscriptions detected in this statement."})

        enriched = identify_merchants_groq(recurring)

        return jsonify({
            "subscriptions": enriched,
            "total_annual_cost": round(sum(r["annual_cost"] for r in enriched), 2),
            "count": len(enriched)
        })
    except Exception as e:
        print(f"subscription_scan error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.unlink(pdf_path)
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
    """Matches your existing verify_and_decode() HMAC pattern exactly."""
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json()
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


"""
4. One more import needed - your file doesn't currently import `datetime`
   as a class directly (only `from datetime import datetime` - check, you
   may already have this at line 9). If not already present, this helper
   file uses `datetime.strptime` so confirm line 9 has:
       from datetime import datetime
   (Looking at your file, line 9 already has this - no change needed.)
"""
