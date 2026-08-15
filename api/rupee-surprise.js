// api/rupee-surprise.js
//
// Generates one fresh "surprise card" message per request using the Claude API.
// This endpoint intentionally does NOT verify payment — the ₹1 Surprise page
// uses a self-attested UPI flow (scan QR, click "I have paid"), same as
// disclosed in the page's own FAQ. Do not copy this no-verification pattern
// onto any endpoint that gates something of real value.
//
// Requires env var: ANTHROPIC_API_KEY

const CATEGORIES = [
  'Encouragement', 'Kindness', 'Confidence', 'Happiness', 'Funny',
  'Curiosity', 'Mini Challenge'
];

// Used only if the Claude API call fails, so the page never breaks.
const FALLBACK = [
  { cat: 'Encouragement', title: 'KEEP GOING', body: 'You are stronger than you think.' },
  { cat: 'Happiness', title: 'JOY', body: 'Your word today: joy.' },
  { cat: 'Kindness', title: 'ONE SMILE', body: "Today's mission: make one person smile." },
];

module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const avoid = Array.isArray(req.body && req.body.avoid) ? req.body.avoid.slice(-20) : [];
  const category = CATEGORIES[Math.floor(Math.random() * CATEGORIES.length)];

  const prompt = `You write short "scratch card" surprise messages for a ₹1 novelty website in India.

Write ONE new message in the category: ${category}.

Rules:
- "title": 1-4 words, punchy, ALL CAPS (like a scratch-card headline).
- "body": one warm, plain-English sentence, under 20 words, no clichés, no emojis, no hashtags.
- Never mention money, prizes, winning, cash, luck, gambling, or investments.
- Make it feel human and specific, not generic.
- Do not repeat or closely resemble any of these already-shown titles: ${avoid.length ? avoid.join(', ') : '(none yet)'}

Respond with ONLY valid JSON, no markdown, no explanation:
{"cat": "${category}", "title": "...", "body": "..."}`;

  try {
    const aiRes = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': process.env.ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-6',
        max_tokens: 200,
        temperature: 1,
        messages: [{ role: 'user', content: prompt }],
      }),
    });

    if (!aiRes.ok) throw new Error('Claude API error: ' + aiRes.status);

    const data = await aiRes.json();
    const raw = (data.content || []).find(b => b.type === 'text');
    if (!raw || !raw.text) throw new Error('No text in Claude response');

    const cleaned = raw.text.replace(/```json|```/g, '').trim();
    const parsed = JSON.parse(cleaned);

    if (!parsed.title || !parsed.body) throw new Error('Malformed message JSON');

    return res.status(200).json({
      cat: parsed.cat || category,
      title: String(parsed.title).slice(0, 40),
      body: String(parsed.body).slice(0, 160),
    });
  } catch (err) {
    console.error('rupee-surprise generation failed:', err);
    const fb = FALLBACK[Math.floor(Math.random() * FALLBACK.length)];
    return res.status(200).json(fb);
  }
};
