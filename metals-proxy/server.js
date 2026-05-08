const express = require("express");
const cors = require("cors");

const app = express();
const PORT = process.env.PORT || 3000;

// Allow requests only from your domain
app.use(cors({
  origin: [
    "https://salarybit.in",
    "https://www.salarybit.in",
    "http://localhost:3000" // for local testing
  ]
}));

// Cache rates in memory — refresh every 30 minutes
let cache = { data: null, fetchedAt: 0 };
const CACHE_TTL = 30 * 60 * 1000;

app.get("/api/metals", async (req, res) => {
  try {
    const now = Date.now();

    // Return cached data if still fresh
    if (cache.data && (now - cache.fetchedAt) < CACHE_TTL) {
      return res.json({ ...cache.data, cached: true });
    }

    // Fetch fresh from MetalpriceAPI — key is secret here on the server
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
    // India retail price = spot + import duty (~10%) + GST (3%) + margin
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

    // Save to cache
    cache = { data: result, fetchedAt: now };

    res.json(result);
  } catch (err) {
    console.error("Error fetching metals:", err);
    res.status(500).json({ error: "Server error" });
  }
});

// Health check — Railway uses this to confirm the app is running
app.get("/health", (req, res) => {
  res.json({ status: "ok", service: "salarybit-metals-proxy" });
});

app.listen(PORT, () => {
  console.log(`Metals proxy running on port ${PORT}`);
});
