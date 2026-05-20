// api/rewrite-resume.js
const crypto = require('crypto');

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { resume, jd, razorpay_payment_id, razorpay_order_id, razorpay_signature } = req.body;

  if (!resume || !jd) return res.status(400).json({ error: 'Resume and job description required.' });
  if (!razorpay_payment_id || !razorpay_order_id || !razorpay_signature) {
    return res.status(400).json({ error: 'Payment verification fields missing.' });
  }

  // Verify Razorpay signature
  const expected = crypto
    .createHmac('sha256', process.env.RAZORPAY_KEY_SECRET)
    .update(razorpay_order_id + '|' + razorpay_payment_id)
    .digest('hex');

  if (expected !== razorpay_signature) {
    return res.status(400).json({ error: 'Payment verification failed.' });
  }

  const prompt = `You are an expert ATS resume optimizer for the Indian job market.

RESUME:
${resume}

JOB DESCRIPTION:
${jd}

Respond ONLY with valid JSON, no markdown, no explanation:
{
  "ats_before": <integer 0-100>,
  "ats_after": <integer 0-100>,
  "present_keywords": [<array of strings>],
  "missing_keywords": [<array of strings>],
  "interview_tips": [<array of 5 strings>],
  "rewritten_resume": "<full rewritten resume as plain text>"
}`;

  try {
    const groqRes = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + process.env.GROQ_API_KEY,
      },
      body: JSON.stringify({
        model: 'llama-3.3-70b-versatile',
        temperature: 0.3,
        max_tokens: 4096,
        messages: [{ role: 'user', content: prompt }],
      }),
    });

    const data = await groqRes.json();
    le
