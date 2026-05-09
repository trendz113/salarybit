const express = require("express");
const cors = require("cors");

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors({
  origin: [
    "https://salarybit.in",
    "https://www.salarybit.in",
    "http://localhost:3000"
  ]
}));

app.use(express.json());

// Cache rates in memory — refresh every 30 minutes
let cache = { data: null, fetchedAt: 0 };
const CACHE_TTL = 30 * 60 * 1000;

// ── METALS API ────────────────────────────────────────────
app.get("/api/metals", async (req, res) => {
  try {
    const now = Date.now();

    if (cache.data && (now - cache.fetchedAt) < CACHE_TTL) {
      return res.json({ ...cache.data, cached: true });
    }

    const API_KEY = process.env.METALS_API_KEY;
    if (!API_KEY) {
      return res.status(500).json({ error: "API key not configured" });
    }

    const response = await fetch(
      `https://api.metalpriceapi.com/v1/latest?api_key=${API_KEY}&base=USD&currencies=XAU,XAG,INR`
    );
    const data = await response.json();

    if (!data.success) {
      return res.status(502).json({ error: "Upstream API error", detail: data });
    }

    const inrPerUsd = data.rates.INR || 83.5;
    const OZ = 31.1035;
    const GOLD_INDIA_MARKUP   = 1.0946;
    const SILVER_INDIA_MARKUP = 1.03;
    const goldG   = (1 / data.rates.XAU) * inrPerUsd / OZ * GOLD_INDIA_MARKUP;
    const silverG = (1 / data.rates.XAG) * inrPerUsd / OZ * SILVER_INDIA_MARKUP;

    const result = {
      updatedAt: new Date().toISOString(),
      inrPerUsd,
      gold: {
        "24K": parseFloat(goldG.toFixed(2)),
        "22K": parseFloat((goldG * 22 / 24).toFixed(2)),
        "21K": parseFloat((goldG * 21 / 24).toFixed(2)),
        "18K": parseFloat((goldG * 18 / 24).toFixed(2)),
      },
      silver: {
        "999": parseFloat(silverG.toFixed(2)),
        "925": parseFloat((silverG * 0.925).toFixed(2)),
      }
    };

    cache = { data: result, fetchedAt: now };
    res.json(result);
  } catch (err) {
    console.error("Error fetching metals:", err);
    res.status(500).json({ error: "Server error" });
  }
});

// ── AI RESUME REWRITER ────────────────────────────────────
app.post("/api/rewrite-resume", async (req, res) => {
  const { resume, jd } = req.body;

  if (!resume || !jd) {
    return res.status(400).json({ error: "Missing resume or jd" });
  }

  const groqKey = process.env.GROQ_API_KEY;
  if (!groqKey) {
    return res.status(500).json({ error: "GROQ_API_KEY not set on server" });
  }

  const prompt = `You are an expert ATS resume optimizer for the Indian job market.

RESUME:
${resume}

JOB DESCRIPTION:
${jd}

Analyze and respond ONLY with valid JSON, no markdown, no explanation:
{
  "ats_before": <integer 0-100, realistic ATS match score of original resume>,
  "ats_after": <integer 0-100, ATS score after rewriting>,
  "present_keywords": [<array of important keywords from JD already in resume>],
  "missing_keywords": [<array of important keywords from JD missing in resume>],
  "rewritten_resume": "<full rewritten resume, ATS optimized, same facts, better phrasing, keywords added naturally>"
}`;

  try {
    const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${groqKey}`
      },
      body: JSON.stringify({
        model: "llama-3.3-70b-versatile",
        temperature: 0.3,
        max_tokens: 4096,
        messages: [{ role: "user", content: prompt }]
      })
    });

    const data = await response.json();
    if (data.error) return res.status(500).json({ error: data.error.message });

    const raw = data.choices[0].message.content.replace(/```json|```/g, "").trim();
    const parsed = JSON.parse(raw);
    res.json(parsed);

  } catch (err) {
    console.error("rewrite-resume error:", err);
    res.status(500).json({ error: err.message });
  }
});

// ── HEALTH CHECK ──────────────────────────────────────────
app.get("/", (req, res) => {
  res.json({ status: "ok", service: "salarybit-metals-proxy" });
});

app.get("/health", (req, res) => {
  res.json({ status: "ok", service: "salarybit-metals-proxy" });
});

app.listen(PORT, () => {
  console.log(`Metals proxy running on port ${PORT}`);
});
