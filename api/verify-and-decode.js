// api/verify-and-decode.js
// Pure Node.js QR decode — no Python required, works on Vercel

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { IncomingForm } = require('formidable');

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  // ── STEP 1: Parse multipart form ──
  const form = new IncomingForm({ maxFileSize: 10 * 1024 * 1024 });
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

  // ── STEP 2: Verify Razorpay signature ──
  const body = orderId + '|' + paymentId;
  const expected = crypto
    .createHmac('sha256', process.env.RAZORPAY_KEY_SECRET)
    .update(body)
    .digest('hex');

  if (expected !== signature) {
    return res.status(400).json({ success: false, error: 'Payment verification failed.' });
  }

  // ── STEP 3: Decode QR from PDF using Node.js only ──
  const tmpPdf = path.join(os.tmpdir(), `pdf_${Date.now()}.pdf`);

  try {
    fs.copyFileSync(pdfFile.filepath, tmpPdf);

    const { fromPath } = require('pdf2pic');
    const Jimp = require('jimp');
    const jsQR = require('jsqr');
    const pdfParse = require('pdf-parse');

    // Get page count
    const pdfBuffer = fs.readFileSync(tmpPdf);
    const pdfData = await pdfParse(pdfBuffer);
    const pageCount = Math.min(pdfData.numpages, 10);

    // Convert each page to image then scan for QR
    const convert = fromPath(tmpPdf, {
      density: 200,
      saveFilename: `page_${Date.now()}`,
      savePath: os.tmpdir(),
      format: 'png',
      width: 1200,
      height: 1600,
    });

    const results = [];

    for (let pageNum = 1; pageNum <= pageCount; pageNum++) {
      let imgPath = null;
      try {
        const result = await convert(pageNum, { responseType: 'image' });
        imgPath = result.path;

        // Try multiple scales — small QRs need upscaling to decode
        for (const scale of [1, 2, 3]) {
          const image = await Jimp.read(imgPath);
          if (scale > 1) image.scale(scale);
          image.grayscale();

          const { data, width, height } = image.bitmap;
          const rgba = new Uint8ClampedArray(width * height * 4);
          for (let i = 0; i < width * height; i++) {
            rgba[i * 4]     = data[i * 4];
            rgba[i * 4 + 1] = data[i * 4 + 1];
            rgba[i * 4 + 2] = data[i * 4 + 2];
            rgba[i * 4 + 3] = data[i * 4 + 3];
          }

          const decoded = jsQR(rgba, width, height, {
            inversionAttempts: 'attemptBoth',
          });

          if (decoded && decoded.data && decoded.data.includes('+++')) {
            const value = decoded.data;
            const parts = value.split('+++');
            results.push({
              value,
              doc_number: parts[0],
              page: pageNum,
              label: `Page ${pageNum}`,
            });
            break;
          }
        }
      } catch (pageErr) {
        console.error(`Page ${pageNum} error:`, pageErr.message);
      } finally {
        if (imgPath && fs.existsSync(imgPath)) {
          try { fs.unlinkSync(imgPath); } catch {}
        }
      }
    }

    // Cleanup
    try { fs.unlinkSync(tmpPdf); } catch {}
    try { fs.unlinkSync(pdfFile.filepath); } catch {}

    if (results.length === 0) {
      return res.status(200).json({
        success: false,
        error: 'No QR code found in this PDF. A refund will be processed within 24 hours.',
      });
    }

    return res.status(200).json({
      success: true,
      qr_strings: results,
      count: results.length,
    });

  } catch (err) {
    try { fs.unlinkSync(tmpPdf); } catch {}
    try { fs.unlinkSync(pdfFile.filepath); } catch {}
    console.error('verify-and-decode error:', err);
    return res.status(500).json({ success: false, error: 'Decode failed: ' + err.message });
  }
};
