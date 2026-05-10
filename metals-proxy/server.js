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

// ─────────────────────────────────────────
// METALS PROXY (existing)
// ─────────────────────────────────────────
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

// ─────────────────────────────────────────
// RESUME REWRITER (new)
// ─────────────────────────────────────────
app.post("/api/rewrite-resume", async (req, res) => {
  try {
    const { resume, jd } = req.body;
    if (!resume || !jd) {
      return res.status(400).json({ error: "resume and jd are required" });
    }

    const GROQ_KEY = process.env.GROQ_API_KEY;
    if (!GROQ_KEY) return res.status(500).json({ error: "Groq API key not configured" });

    const prompt = `You are an expert ATS resume optimiser. Analyse the resume against the job description and return a JSON response.

RESUME:
${resume}

JOB DESCRIPTION:
${jd}

Return ONLY valid JSON (no markdown, no backticks, no explanation) with this exact structure:
{
  "ats_before": <number 0-100>,
  "ats_after": <number 0-100>,
  "present_keywords": ["keyword1", "keyword2"],
  "missing_keywords": ["keyword1", "keyword2"],
  "rewritten_resume": "FULL RESUME TEXT HERE"
}

For rewritten_resume, use this EXACT format with these EXACT section headers:

[Full Name]
[Job Title] | [email] | [phone] | [city]

SUMMARY
[Write 2 strong sentences tailored to the job description]

EXPERIENCE
[Job Title] | [Company Name] | [Start Year] – [End Year or Present]
- [Achievement bullet using action verb + result + JD keyword]
- [Achievement bullet using action verb + result + JD keyword]
- [Achievement bullet using action verb + result + JD keyword]
- [Achievement bullet using action verb + result + JD keyword]

SKILLS
[skill1], [skill2], [skill3], [skill4], [skill5], [skill6], [skill7], [skill8]

EDUCATION
[Degree] in [Field] | [University Name] | [Year]

STRICT RULES — you must follow these exactly:
1. Section headers (SUMMARY, EXPERIENCE, SKILLS, EDUCATION) must be ALL CAPS alone on their own line
2. Every bullet point under EXPERIENCE must start with "- " (dash space)
3. Bullets must use strong action verbs: Designed, Developed, Built, Optimised, Delivered, Led, Implemented, Managed
4. Do NOT invent any company names, degrees, or dates — only use facts from the original resume
5. Naturally weave in the missing keywords from the JD into the bullets
6. Return ONLY the JSON — no other text before or after`;

    const groqResp = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${GROQ_KEY}`
      },
      body: JSON.stringify({
        model: "llama3-70b-8192",
        messages: [{ role: "user", content: prompt }],
        temperature: 0.3,
        max_tokens: 2000
      })
    });

    const groqData = await groqResp.json();

    if (!groqData.choices || !groqData.choices[0]) {
      return res.status(502).json({ error: "Groq returned no response", detail: groqData });
    }

    const raw = groqData.choices[0].message.content.trim();

    // Strip markdown fences if Groq adds them
    const clean = raw.replace(/^```json\s*/i, "").replace(/^```\s*/i, "").replace(/```\s*$/i, "").trim();

    let parsed;
    try {
      parsed = JSON.parse(clean);
    } catch (e) {
      // If JSON parse fails, return the raw text so frontend can still use it
      return res.json({
        ats_before: 30,
        ats_after: 70,
        present_keywords: [],
        missing_keywords: [],
        rewritten_resume: clean
      });
    }

    res.json(parsed);

  } catch (err) {
    console.error("Resume rewrite error:", err);
    res.status(500).json({ error: "Server error: " + err.message });
  }
});

// ─────────────────────────────────────────
// HEALTH CHECK
// ─────────────────────────────────────────
app.get("/health", (req, res) => {
  res.json({ status: "ok", service: "salarybit-proxy" });
});

app.listen(PORT, () => {
  console.log(`Proxy running on port ${PORT}`);
});
