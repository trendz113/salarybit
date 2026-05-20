const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const os = require('os');

function parseMultipart(event) {
  return new Promise((resolve, reject) => {
    const Busboy = require('busboy');
    const busboy = Busboy({ headers: event.headers });

    const fields = {};
    let pdfBuffer = null;

    busboy.on('field', (name, value) => {
      fields[name] = value;
    });

    busboy.on('file', (name, file) => {
      if (name === 'pdf') {
        const chunks = [];
        file.on('data', (chunk) => chunks.push(chunk));
        file.on('end', () => { pdfBuffer = Buffer.concat(chunks); });
      } else {
        file.resume();
      }
    });

    busboy.on('finish', () => resolve({ fields, pdfBuffer }));
    busboy.on('error', reject);

    const body = event.isBase64Encoded
      ? Buffer.from(event.body, 'base64')
      : Buffer.from(event.body || '', 'utf8');

    busboy.end(body);
  });
}

exports.handler = async (event) => {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };

  if (event.httpMethod === 'OPTIONS') return { statusCode: 200, headers, body: '' };
  if (event.httpMethod !== 'POST') return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };

  let parsed;
  try {
    parsed = await parseMultipart(event);
  } catch (err) {
    return { statusCode: 400, headers, body: JSON.stringify({ success: false, error: 'Could not parse form: ' + err.message }) };
  }

  const { fields, pdfBuffer } = parsed;
  const orderId   = fields.razorpay_order_id;
  const paymentId = fields.razorpay_payment_id;
  const signature = fields.razorpay_signature;

  if (!orderId || !paymentId || !signature || !pdfBuffer) {
    return { statusCode: 400, headers, body: JSON.stringify({ success: false, error: 'Missing required fields.' }) };
  }

  // Verify Razorpay signature
  const sigBody = orderId + '|' + paymentId;
  const expected = crypto
    .createHmac('sha256', process.env.RAZORPAY_KEY_SECRET)
    .update(sigBody)
    .digest('hex');

  if (expected !== signature) {
    return { statusCode: 400, headers, body: JSON.stringify({ success: false, error: 'Payment verification failed.' }) };
  }

  const tmpPdf = path.join(os.tmpdir(), `pdf_${Date.now()}.pdf`);

  try {
    fs.writeFileSync(tmpPdf, pdfBuffer);

    const { fromPath } = require('pdf2pic');
    const Jimp = require('jimp');
    const jsQR = require('jsqr');
    const pdfParse = require('pdf-parse');

    const pdfData = await pdfParse(pdfBuffer);
    const pageCount = Math.min(pdfData.numpages, 10);

    // Render at lower density — QR codes decode fine at 150 DPI and it avoids OOM
    const convert = fromPath(tmpPdf, {
      density: 150,
      saveFilename: `page_${Date.now()}`,
      savePath: os.tmpdir(),
      format: 'png',
      width: 800,
      height: 1100,
    });

    const results = [];
    const seen = new Set();

    for (let pageNum = 1; pageNum <= pageCount; pageNum++) {
      let imgPath = null;
      try {
        const result = await convert(pageNum, { responseType: 'image' });
        imgPath = result.path;

        for (const scale of [1, 2]) {
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
          image.bitmap.data = null; // release bitmap memory immediately

          const decoded = jsQR(rgba, width, height, {
            inversionAttempts: 'attemptBoth',
          });

          if (decoded && decoded.data && !seen.has(decoded.data)) {
            seen.add(decoded.data);
            const value = decoded.data;
            const parts = value.includes('+++') ? value.split('+++') : [value, ''];
            results.push({
              value,
              doc_number: parts[0],
              page: pageNum,
              label: `Page ${pageNum}`,
            });
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

    try { fs.unlinkSync(tmpPdf); } catch {}

    if (results.length === 0) {
      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({
          success: false,
          error: 'No QR code found in this PDF. A refund will be processed within 24 hours.',
        }),
      };
    }

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ success: true, qr_strings: results, count: results.length }),
    };

  } catch (err) {
    try { fs.unlinkSync(tmpPdf); } catch {}
    console.error('verify-and-decode error:', err);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ success: false, error: 'Decode failed: ' + err.message }),
    };
  }
};
