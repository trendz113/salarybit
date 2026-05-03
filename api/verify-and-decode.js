// api/verify-and-decode.js
const crypto = require('crypto');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');
const formidable = require('formidable');

function ensureDeps() {
  try {
    execSync('python3 -c "import fitz, pyzbar"', { stdio: 'ignore' });
  } catch {
    execSync('pip install pymupdf pyzbar pillow --quiet', { stdio: 'ignore' });
  }
}

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  // Parse multipart form
  const form = formidable({ maxFileSize: 10 * 1024 * 1024 });
  let fields, files;
  try {
    [fields, files] = await form.parse(req);
  } catch (err) {
    return res.status(400).json({ success: false, error: 'Could not parse form: ' + err.message });
  }

  const orderId   = Array.isArray(fields.razorpay_order_id)   ? fields.razorpay_order_id[0]   : fields.razorpay_order_id;
  const paymentId = Array.isArray(fields.razorpay_payment_id) ? fields.razorpay_payment_id[0] : fields.razorpay_payment_id;
  const signature = Array.isArray(fields.razorpay_signature)  ? fields.razorpay_signature[0]  : fields.razorpay_signature;
  const pdfFile   = Array.isArray(files.pdf) ? files.pdf[0] : files.pdf;

  if (!orderId || !paymentId || !signature || !pdfFile) {
    return res.status(400).json({ success: false, error: 'Missing required fields.' });
  }

  // Verify Razorpay signature
  const body = orderId + '|' + paymentId;
  const expected = crypto
    .createHmac('sha256', process.env.RAZORPAY_KEY_SECRET)
    .update(body)
    .digest('hex');

  if (expected !== signature) {
    return res.status(400).json({ success: false, error: 'Payment verification failed.' });
  }

  // Decode QR from PDF
  const tmpPdf    = path.join(os.tmpdir(), `pdf_${Date.now()}.pdf`);
  const tmpOut    = path.join(os.tmpdir(), `out_${Date.now()}.json`);
  const scriptPath = path.join(os.tmpdir(), `qr_decode_${Date.now()}.py`);

  try {
    fs.copyFileSync(pdfFile.filepath, tmpPdf);
    ensureDeps();

    const pyScript = `
import fitz, json, sys
from PIL import Image
from pyzbar.pyzbar import decode
import io

pdf_path = sys.argv[1]
out_path  = sys.argv[2]

doc = fitz.open(pdf_path)
results = []

for page_num in range(doc.page_count):
    page = doc[page_num]
    img_list = page.get_images(full=True)

    for img_info in img_list:
        xref = img_info[0]
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

        if decoded and "+++" in decoded:
            parts = decoded.split("+++", 1)
            results.append({
                "value": decoded,
                "doc_number": parts[0],
                "page": page_num + 1,
                "label": f"Page {page_num + 1}"
            })

with open(out_path, "w") as f:
    json.dump(results, f)
`;

    fs.writeFileSync(scriptPath, pyScript);
    execSync(`python3 ${scriptPath} ${tmpPdf} ${tmpOut}`, { timeout: 30000 });

    const qrStrings = JSON.parse(fs.readFileSync(tmpOut, 'utf-8'));

    // Cleanup all temp files
    [tmpPdf, tmpOut, scriptPath, pdfFile.filepath].forEach(f => {
      try { fs.unlinkSync(f); } catch {}
    });

    if (qrStrings.length === 0) {
      return res.status(200).json({
        success: false,
        error: 'No QR code found in this PDF. A refund will be processed within 24 hours.'
      });
    }

    return res.status(200).json({
      success: true,
      qr_strings: qrStrings,
      count: qrStrings.length
    });

  } catch (err) {
    [tmpPdf, tmpOut, scriptPath].forEach(f => { try { fs.unlinkSync(f); } catch {} });
    return res.status(500).json({ success: false, error: 'Decode failed: ' + err.message });
  }
};
