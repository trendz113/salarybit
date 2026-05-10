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

// Required to parse JSON POST bodies
app.use(express.json());

// ─── METALS ──────────────────────────────────────────────────────────────────

let cache = { data: null, fetchedAt: 0 };
const CACHE_TTL = 30 * 60 * 1000;

app.get("/api/metals", async (req, res) => {
  try {
    const now = Date.now();
    if (cache.data && (now - cache.fetchedAt) < CACHE_TTL) {
      return res.json({ ...cache.data, cached: true });
    }

    const API_KEY = process.env.METALS_API_KEY;
    if (!API_KEY) return res.status(500).json({ error: "API key not configured" });

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

// ─── RESUME REWRITER ─────────────────────────────────────────────────────────

app.post("/api/rewrite-resume", async (req, res) => {
  try {
    const { resume, jd } = req.body || {};

    if (!resume || !jd) {
      return res.status(400).json({ error: "Both 'resume' and 'jd' are required." });
    }

    const GROQ_API_KEY = process.env.GROQ_API_KEY;
    if (!GROQ_API_KEY) {
      return res.status(500).json({ error: "GROQ_API_KEY not set in environment." });
    }

    const prompt = `You are an expert ATS resume optimizer.

Given the resume and job description below, return ONLY a raw JSON object — no markdown, no backticks, no explanation, no text before or after. Just the JSON.

JSON shape:
{
  "ats_before": <integer 0-100>,
  "ats_after": <integer 0-100>,
  "present_keywords": ["keyword1", "keyword2"],
  "missing_keywords": ["keyword3", "keyword4"],
  "rewritten_resume": "Full rewritten resume as plain text. Use \\n for line breaks."
}

Rules:
- ats_before: ATS score of the ORIGINAL resume vs the JD (0-100)
- ats_after: ATS score of the REWRITTEN resume vs the JD (0-100)
- present_keywords: keywords already in the original resume that match the JD
- missing_keywords: important JD keywords NOT in the original resume (weave them into the rewrite naturally)
- rewritten_resume: the full rewritten resume as plain text only — NO JSON inside this field, just the resume text

RESUME:
${resume}

JOB DESCRIPTION:
${jd}`;

    const groqRes = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${GROQ_API_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: "llama-3.3-70b-versatile",   // ✅ FIXED: was llama3-70b-8192 (wrong)
        temperature: 0.3,
        max_tokens: 3000,
        messages: [{ role: "user", content: prompt }]
      })
    });

    if (!groqRes.ok) {
      const errText = await groqRes.text();
      console.error("Groq error:", errText);
      return res.status(502).json({ error: "Groq API error", detail: errText });
    }

    const groqData = await groqRes.json();
    const rawText = groqData.choices?.[0]?.message?.content || "";

    // Strip markdown fences the model sometimes wraps around JSON
    const cleaned = rawText
      .replace(/^```json\s*/i, "")
      .replace(/^```\s*/i, "")
      .replace(/```\s*$/i, "")
      .trim();

    let parsed;
    try {
      parsed = JSON.parse(cleaned);
    } catch (e) {
      console.error("JSON parse failed. Raw:", rawText);
      return res.status(500).json({ error: "AI returned invalid JSON. Please try again.", raw: rawText });
    }

    if (typeof parsed.ats_before === "undefined" || !parsed.rewritten_resume) {
      return res.status(500).json({ error: "AI response missing required fields.", raw: rawText });
    }

    res.json(parsed);

  } catch (err) {
    console.error("Resume rewrite error:", err);
    res.status(500).json({ error: "Server error: " + err.message });
  }
});

// ─── HEALTH ──────────────────────────────────────────────────────────────────

app.get("/health", (req, res) => {
  res.json({ status: "ok", service: "salarybit-metals-proxy" });
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
