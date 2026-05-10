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

    const prompt = `You are an expert ATS resume writer. Rewrite the candidate's resume to match the job description.

STRICT OUTPUT RULES:
- Return ONLY a valid JSON object. No markdown, no backticks, no explanation.
- The "rewritten_resume" field must be a properly structured resume in plain text.
- The resume MUST use these exact section headers on their own line in ALL CAPS: SUMMARY, EXPERIENCE, EDUCATION, SKILLS
- Each job must follow this exact format:
  Job Title — Company Name
  Month Year – Month Year (or Present)
  • bullet point achievement with metric if possible
  • bullet point achievement
  • bullet point achievement
- SKILLS section must list skills as comma-separated keywords, NOT paragraphs
- Do NOT write paragraphs for experience — use bullet points ONLY
- Do NOT write a narrative or story — this is a resume, not a cover letter
- Naturally weave missing JD keywords into bullets and skills
- Keep it concise: max 600 words in the resume text

JSON format to return:
{
  "ats_before": <integer 0-100>,
  "ats_after": <integer 0-100>,
  "present_keywords": ["keyword1", "keyword2"],
  "missing_keywords": ["keyword3", "keyword4"],
  "interview_tips": ["tip1", "tip2", "tip3", "tip4", "tip5"],
  "rewritten_resume": "FULL RESUME TEXT HERE with \\n for line breaks"
}

Field rules:
- ats_before: ATS score of original resume vs JD
- ats_after: ATS score of rewritten resume vs JD (must be higher)
- present_keywords: keywords already in the original resume matching JD
- missing_keywords: important JD keywords that were missing (now added to rewrite)
- interview_tips: 5 specific, actionable tips to prepare for THIS job interview based on the JD
- rewritten_resume: the full structured resume — name, contact, SUMMARY, EXPERIENCE with bullets, EDUCATION, SKILLS

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
        model: "llama-3.3-70b-versatile",
        temperature: 0.2,
        max_tokens: 3500,
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
