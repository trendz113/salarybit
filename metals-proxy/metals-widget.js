/**
 * SalaryBit — Gold & Silver Rates Widget
 * Calls your secure Railway proxy — API key is never exposed in the browser.
 *
 * Embed: <div id="sb-metals-widget"></div><script src="/metals-widget.js"></script>
 *
 * After deploying to Railway, update PROXY_URL below with your Railway URL.
 */

(function () {
  // ✅ Update this to your Railway app URL after deploying
  const PROXY_URL = "https://web-production-456eb.up.railway.app";

  const TOLA = 11.6638;
  const OZ   = 31.1035;
  let R = {};

  const STYLE = `
    #sb-metals-widget * { box-sizing: border-box; margin: 0; padding: 0; }
    #sb-metals-widget {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-size: 14px; color: #1a1a2e; max-width: 820px;
    }
    .sbw-ticker { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 1rem; }
    .sbw-tc { background: #fff; border: 1px solid #e8eaf6; border-radius: 10px; padding: 0.85rem 1rem; }
    .sbw-tc.gold   { border-top: 3px solid #f59e0b; }
    .sbw-tc.silver { border-top: 3px solid #94a3b8; }
    .sbw-tc-label { font-size: 11px; color: #999; margin-bottom: 3px; }
    .sbw-tc-val   { font-size: 20px; font-weight: 700; color: #1a1a2e; }
    .sbw-tc-sub   { font-size: 11px; color: #bbb; margin-top: 2px; }
    .sbw-card { background: #fff; border: 1px solid #e8eaf6; border-radius: 12px; padding: 1rem 1.2rem; margin-bottom: 1rem; }
    .sbw-title { font-size: 12px; font-weight: 600; color: #5b6af0; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.75rem; }
    .sbw-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .sbw-table th { font-size: 11px; color: #aaa; font-weight: 400; text-align: left; padding: 0 0 6px; border-bottom: 1px solid #f0f1f8; }
    .sbw-table th:not(:first-child) { text-align: right; }
    .sbw-table td { padding: 8px 0; border-bottom: 1px solid #f7f8fc; color: #333; }
    .sbw-table tr:last-child td { border-bottom: none; }
    .sbw-table td:not(:first-child) { text-align: right; font-weight: 500; color: #1a1a2e; }
    .sbw-calc-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
    .sbw-calc-row select, .sbw-calc-row input { padding: 7px 9px; border: 1px solid #dde1f7; border-radius: 7px; font-size: 13px; color: #1a1a2e; background: #fff; outline: none; }
    .sbw-calc-row select:focus, .sbw-calc-row input:focus { border-color: #5b6af0; }
    .sbw-calc-row input { width: 110px; }
    .sbw-result { background: #5b6af0; border-radius: 8px; padding: 0.75rem 1rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .sbw-result-label { font-size: 12px; color: rgba(255,255,255,0.8); }
    .sbw-result-val   { font-size: 20px; font-weight: 700; color: #fff; }
    .sbw-status { font-size: 11px; color: #aaa; margin-bottom: 0.75rem; display: flex; align-items: center; gap: 6px; }
    .sbw-dot { width: 7px; height: 7px; border-radius: 50%; background: #f59e0b; flex-shrink: 0; }
    .sbw-note { font-size: 11px; color: #92400e; background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 5px 8px; margin-top: 8px; }
    .sbw-footer { font-size: 11px; color: #bbb; text-align: center; margin-top: 0.75rem; }
    .sbw-footer a { color: #5b6af0; text-decoration: none; }
  `;

  function inr(n) { return "₹" + Math.round(n).toLocaleString("en-IN"); }

  function render() {
    document.getElementById("sbw-g24").textContent = inr(R.gold24);
    document.getElementById("sbw-g22").textContent = inr(R.gold22);
    document.getElementById("sbw-ag").textContent  = "₹" + R.silver.toFixed(2);

    document.getElementById("sbw-gold-rows").innerHTML = [
      ["24K — Pure gold",          R.gold24],
      ["22K — Hallmark jewellery", R.gold22],
      ["21K",                      R.gold21],
      ["18K — Mixed jewellery",    R.gold18],
    ].map(([k,p]) => `<tr><td>${k}</td><td>${inr(p)}</td><td>${inr(p*10)}</td><td>${inr(p*TOLA)}</td></tr>`).join("");

    document.getElementById("sbw-silver-rows").innerHTML = [
      ["Per gram",    R.silver],
      ["Per 10 grams",R.silver*10],
      ["Per tola",    R.silver*TOLA],
      ["Per 100 grams",R.silver*100],
      ["Per kg",      R.silver*1000],
    ].map(([u,p]) => `<tr><td>${u}</td><td>${p < 200 ? "₹"+p.toFixed(2) : inr(p)}</td></tr>`).join("");

    calcPrice();
  }

  function calcPrice() {
    const metal  = document.getElementById("sbw-metal").value;
    const weight = parseFloat(document.getElementById("sbw-weight").value) || 0;
    const unit   = document.getElementById("sbw-unit").value;
    let grams = weight;
    if (unit === "tola") grams = weight * TOLA;
    if (unit === "oz")   grams = weight * OZ;
    if (unit === "kg")   grams = weight * 1000;
    const labels = { gold24:"Gold 24K", gold22:"Gold 22K", gold21:"Gold 21K", gold18:"Gold 18K", silver:"Silver" };
    const ul = { gram:"g", tola:" tola", oz:" oz", kg:" kg" };
    document.getElementById("sbw-calc-desc").textContent = weight + ul[unit] + " of " + labels[metal];
    document.getElementById("sbw-calc-val").textContent  = R[metal] > 0 ? inr((R[metal]||0)*grams) : "—";
  }

  async function fetchRates() {
    try {
      const res  = await fetch(`${PROXY_URL}/api/metals`);
      const data = await res.json();
      if (data.gold && data.silver) {
        R = { gold24:data.gold["24K"], gold22:data.gold["22K"], gold21:data.gold["21K"], gold18:data.gold["18K"], silver:data.silver["999"] };
        const dot = document.getElementById("sbw-dot");
        if (dot) dot.style.background = "#22c55e";
        const time = new Date(data.updatedAt).toLocaleTimeString("en-IN", { hour:"2-digit", minute:"2-digit" });
        document.getElementById("sbw-status-txt").textContent = "Live rates · " + time;
        render();
        return;
      }
    } catch(e) { console.warn("Metals proxy error:", e); }
    R = { gold24:7320, gold22:7320*(22/24), gold21:7320*(21/24), gold18:7320*(18/24), silver:91.5 };
    document.getElementById("sbw-status-txt").textContent = "Reference rates · Proxy offline";
    render();
  }

  function init() {
    const root = document.getElementById("sb-metals-widget");
    if (!root) return;
    const style = document.createElement("style");
    style.textContent = STYLE;
    document.head.appendChild(style);
    root.innerHTML = `
      <div class="sbw-status"><span class="sbw-dot" id="sbw-dot"></span><span id="sbw-status-txt">Loading rates...</span></div>
      <div class="sbw-ticker">
        <div class="sbw-tc gold"><div class="sbw-tc-label">Gold 24K / gram</div><div class="sbw-tc-val" id="sbw-g24">—</div><div class="sbw-tc-sub">INR</div></div>
        <div class="sbw-tc gold"><div class="sbw-tc-label">Gold 22K / gram</div><div class="sbw-tc-val" id="sbw-g22">—</div><div class="sbw-tc-sub">INR</div></div>
        <div class="sbw-tc silver"><div class="sbw-tc-label">Silver / gram</div><div class="sbw-tc-val" id="sbw-ag">—</div><div class="sbw-tc-sub">INR</div></div>
      </div>
      <div class="sbw-card">
        <div class="sbw-title">🥇 Gold rates — all karats</div>
        <table class="sbw-table"><thead><tr><th>Karat</th><th>Per gram</th><th>Per 10g</th><th>Per tola</th></tr></thead><tbody id="sbw-gold-rows"></tbody></table>
      </div>
      <div class="sbw-card">
        <div class="sbw-title">🥈 Silver rates</div>
        <table class="sbw-table"><thead><tr><th>Unit</th><th>Price (₹)</th></tr></thead><tbody id="sbw-silver-rows"></tbody></table>
      </div>
      <div class="sbw-card">
        <div class="sbw-title">🧮 Price calculator</div>
        <div class="sbw-calc-row">
          <select id="sbw-metal" onchange="sbwCalc()"><option value="gold24">Gold 24K</option><option value="gold22">Gold 22K</option><option value="gold21">Gold 21K</option><option value="gold18">Gold 18K</option><option value="silver">Silver</option></select>
          <input type="number" id="sbw-weight" value="10" min="0.1" step="0.1" oninput="sbwCalc()" />
          <select id="sbw-unit" onchange="sbwCalc()"><option value="gram">Grams</option><option value="tola">Tola</option><option value="oz">Ounce</option><option value="kg">Kilogram</option></select>
        </div>
        <div class="sbw-result"><span class="sbw-result-label" id="sbw-calc-desc">10g of Gold 24K</span><span class="sbw-result-val" id="sbw-calc-val">—</span></div>
        <div class="sbw-note">⚠️ International spot prices in INR. Jewellery prices include making charges + 3% GST.</div>
      </div>
      <div class="sbw-footer">Rates for reference only · <a href="https://salarybit.in/gold-rate-today.html">Full rates page</a> · <a href="https://salarybit.in">SalaryBit</a></div>
    `;
    window.sbwCalc = calcPrice;
    fetchRates();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
