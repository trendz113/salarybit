const crypto = require('crypto');

exports.handler = async (event) => {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };

  if (event.httpMethod === 'OPTIONS') return { statusCode: 200, headers, body: '' };
  if (event.httpMethod !== 'POST') return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };

  const { resume, jd, razorpay_payment_id, razorpay_order_id, razorpay_signature } = JSON.parse(event.body || '{}');

  if (!resume || !jd) return { statusCode: 400, headers, body: JSON.stringify({ error: 'Resume and job description required.' }) };
  if (!razorpay_payment_id || !razorpay_order_id || !razorpay_signature) {
    return { statusCode: 400, headers, body: JSON.stringify({ error: 'Payment verification fields missing.' }) };
  }

  const expected = crypto
    .createHmac('sha256', process.env.RAZORPAY_KEY_SECRET)
    .update(razorpay_order_id + '|' + razorpay_payment_id)
    .digest('hex');

  if (expected !== razorpay_signature) {
    return { statusCode: 400, headers, body: JSON.stringify({ error: 'Payment verification failed.' }) };
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
    let raw = data.choices[0].message.content.trim().replace(/```json|```/g, '').trim();
    const parsed = JSON.parse(raw);
    return { statusCode: 200, headers, body: JSON.stringify(parsed) };

  } catch (err) {
    return { statusCode: 500, headers, body: JSON.stringify({ error: err.message }) };
  }
};
