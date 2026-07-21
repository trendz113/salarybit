# SalaryBit 💰

**Free salary, tax & financial intelligence platform for Indian professionals**

🔗 Live site: [salarybit.in](https://salarybit.in)

SalaryBit helps salaried employees in India understand their in-hand salary, compare tax regimes, plan insurance, and navigate labour law — all for free, with zero data collection. All calculations run entirely in the browser.

---

## ✨ Features

### Salary & Tax Tools
- **In-Hand Salary Calculator** — CTC to take-home breakdown (FY 2026-27)
- **Old vs New Tax Regime Comparison**
- **Capital Gains Tax Calculator** — Indian, US & Euro shares (STCG/LTCG, DTAA relief)
- **ESOP / RSU Tax Calculator** — Section 17(2) perquisite + capital gains
- **GST & Professional Tax Calculators**

### Loan & Investment Tools
- Home Loan EMI, Car Loan EMI, SIP, FD, EPF/PF, Gratuity, Retirement Planner, Notice Period, Salary Hike

### AI-Powered Tools
- **Tax AI** — Form 16 & AIS analysis with CA-level breakdown
- **Fix Your Finance** — Debt clarity passbook & payoff prioritisation
- **Patience Passbook** — Home loan prepay-vs-invest planner
- **Tax Notice Shield** — Plain-language income tax notice decoder
- **Insurance Mitra** — Personalised term & health insurance advisor
- **Subscription Leak Finder** — Detects forgotten recurring bank/UPI charges
- **MF Analyzer Bot** — Mutual fund portfolio analysis (CAS PDF upload)
- **Family Passbook** — Private "in case of emergency" financial document
- **PDF Signature Validator** & **QR Decoder** — For Form 16, e-Khata, and signed govt. documents

### Other
- Labour Code impact calculator & employee rights guide
- Salary & finance blog

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Static HTML, CSS, JavaScript — no frameworks |
| Hosting | [GitHub Pages](https://pages.github.com/) |
| Backend / API | Python (Flask) — see `server.py`, `api/` |
| Backend hosting | [Railway](https://railway.app/) (`railpack.json`, `nixpacks.toml`, `Procfile`) |
| Payments | Razorpay |
| AI | Groq / Claude APIs |
| PDF processing | pdfplumber |

> **Note:** This repo does not use Vercel or Netlify for production. `vercel.json` is a legacy artifact from earlier hosting and is not part of the current deployment path.

---

## 📁 Project Structure

```
salarybit/
├── index.html              # Homepage
├── about.html               # About page
├── qr-decoder.html          # e-Khata / BBMP QR decoder tool
├── tools/                   # Standalone calculator pages
├── blog/                    # Blog posts & index
├── api/                     # Backend API routes
├── server.py                # Flask backend entrypoint
├── agent.py                 # Automation / content agent script
├── requirements.txt         # Python dependencies
├── Procfile                 # Railway process definition
├── railpack.json            # Railway build config
├── nixpacks.toml            # Railway build config
├── CNAME                    # GitHub Pages custom domain (salarybit.in)
├── sitemap.xml               # SEO sitemap
├── ads.txt                  # Google AdSense verification
└── .github/workflows/       # CI/CD automation
```

---

## 🚀 Local Development

The frontend is fully static — no build step required:

```bash
git clone https://github.com/trendz113/salarybit.git
cd salarybit
# Open index.html directly in a browser, or serve locally:
python3 -m http.server 8000
```

For the backend API:

```bash
pip install -r requirements.txt
python3 server.py
```

---

## 🌐 Deployment

- **Frontend** deploys automatically to GitHub Pages on every push to `main`, via the workflow in `.github/workflows/`.
- **Custom domain** (`salarybit.in`) is configured via the `CNAME` file and DNS.
- **Backend** deploys separately on Railway.

---

## 🔒 Privacy

SalaryBit collects zero personal or financial data. All salary/tax calculations run client-side in the browser. See the full [Privacy Policy](https://salarybit.in/privacy.html).

---

## ⚠️ Disclaimer

SalaryBit provides estimates for informational purposes only and is not a substitute for professional financial, tax, or legal advice. Always consult a qualified Chartered Accountant or financial advisor. Not affiliated with the Government of India, Income Tax Department, EPFO, IRDAI, or SEBI.

---

## 📬 Contact

- Email: tremendouscollections@gmail.com
- Twitter/X: @deepakmba02

---

## 📄 License

© 2026 SalaryBit. All rights reserved.
