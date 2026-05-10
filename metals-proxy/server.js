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

    const prompt = `You are an expert ATS resume writer and interview coach. Rewrite the candidate's resume to match the job description, and provide complete interview preparation advice.

STRICT OUTPUT RULES:
- Return ONLY a valid JSON object. No markdown, no backticks, no explanation.
- The "rewritten_resume" must be a properly structured resume in plain text.
- The resume MUST use these exact section headers on their own line in ALL CAPS: SUMMARY, EXPERIENCE, EDUCATION, SKILLS
- Each job must follow this exact format:
  Job Title — Company Name
  Month Year – Month Year (or Present)
  • bullet point achievement with metric if possible
  • bullet point achievement
- SKILLS section must list skills as comma-separated keywords, NOT paragraphs
- Do NOT write paragraphs for experience — use bullet points ONLY
- Naturally weave missing JD keywords into bullets and skills

For "interview_tips", generate exactly 8 tips covering ALL of these categories — one tip per category:
1. TECHNICAL: One specific technical topic from the JD to study deeply (e.g. "Study Kubernetes pod lifecycle, deployments and services — likely to be asked")
2. PREPARATION: What to research about the company before the interview (culture, products, tech stack)
3. DRESS CODE: Exactly what to wear for this type of role and company (formal, business casual, smart casual — be specific)
4. WHAT TO CARRY: List of everything to bring to the interview (resume copies, ID, notebook, pen, laptop if needed)
5. CALM & MINDSET: One practical tip to stay calm and confident during the interview
6. BODY LANGUAGE: Specific body language advice (eye contact, posture, handshake, when to smile)
7. QUESTIONS TO ASK: One smart question the candidate should ask the interviewer at the end
8. TIMING: When to arrive, how early, what to do while waiting

JSON format to return:
{
  "ats_before": <integer 0-100>,
  "ats_after": <integer 0-100>,
  "present_keywords": ["keyword1", "keyword2"],
  "missing_keywords": ["keyword3", "keyword4"],
  "interview_tips": [
    "TECHNICAL: ...",
    "PREPARATION: ...",
    "DRESS CODE: ...",
    "WHAT TO CARRY: ...",
    "CALM & MINDSET: ...",
    "BODY LANGUAGE: ...",
    "QUESTIONS TO ASK: ...",
    "TIMING: ..."
  ],
  "rewritten_resume": "FULL RESUME TEXT HERE with \\n for line breaks"
}

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
        max_tokens: 4000,
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
