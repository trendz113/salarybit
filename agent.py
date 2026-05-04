"""
SalaryBit Article Agent
========================
Writes new SEO-optimised blog articles for salarybit.in.

What this agent does:
  - Picks the next unpublished topic from NEW_TOPICS
  - Calls Groq to generate a full, styled HTML article
  - Saves it to the blog/ folder
  - Appends a card to blog/index.html
  - Regenerates sitemap.xml

What this agent does NOT do:
  - It never rewrites, cleans, or touches any existing article.
  - It never changes style decisions you made manually.

Usage:
  python agent.py              # write one article
  python agent.py --all        # write all remaining articles
"""

import os
import re
import sys
import json
import time
from datetime import datetime
from groq import Groq

# ── Config ────────────────────────────────────────────────────────────────────
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

BLOG_FOLDER      = "blog"
PUBLISHED_FILE   = "published_topics.json"   # tracks written topics
SITEMAP_PATH     = "sitemap.xml"
BLOG_INDEX_PATH  = "blog/index.html"
SITE_URL         = "https://salarybit.in"

# Your AdSense publisher ID — replace with your real one
ADSENSE_PUB_ID   = "ca-pub-XXXXXXXXXXXXXXXX"

# Placeholder image used when no real image is provided.
# Replace with the real CDN path once you upload topic-specific images.
DEFAULT_OG_IMAGE = f"{SITE_URL}/assets/images/salarybit-og.png"

# ── Topics ────────────────────────────────────────────────────────────────────
NEW_TOPICS = [
    "TCS software engineer salary in India 2026",
    "Infosys fresher salary package 2026",
    "Government teacher salary India state wise",
    "IAS officer salary and perks India",
    "Data scientist salary in India 2026",
    "Bank PO salary after 7th pay commission",
    "Amazon India software developer salary",
    "Doctor salary government hospital India",
    "MBA fresher salary in India 2026",
    "CA salary in India after articleship",
    "HRA calculation formula India",
    "PF deduction calculation guide India",
    "Income tax slab 2026-27 India",
    "How to calculate take home salary India",
    "Average salary in India by profession 2026",
    "Nurse salary India government vs private",
    "Army soldier salary in India 2026",
    "Police constable salary state wise India",
    "Software engineer salary Hyderabad vs Bangalore",
    "Wipro salary hike 2026",
    "Layoff compensation India 2026",
    "PAN card apply online India guide",
    "Duplicate PAN card application process",
    "EPF withdrawal process India 2026",
    "Gratuity calculation formula India",
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def make_slug(topic: str) -> str:
    slug = topic.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    return slug[:70]

def call_groq(prompt: str, max_tokens: int = 6000) -> str:
    """Call Groq with retry logic."""
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            time.sleep(30)
    raise RuntimeError("Groq API failed after 3 attempts.")

def strip_markdown_fences(text: str) -> str:
    """Remove ```html or ``` wrappers that the model sometimes adds."""
    text = re.sub(r"^```[a-z]*\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text.strip())
    return text.strip()

# ── The master HTML template injected into every prompt ───────────────────────
def build_prompt(topic: str, slug: str, today: str) -> str:
    canonical = f"{SITE_URL}/blog/{slug}.html"
    og_image  = f"{SITE_URL}/blog/images/{slug}.png"

    # Full design system spelled out for the model so it never deviates
    return f"""You are a senior content writer AND front-end developer for salarybit.in, an Indian salary and personal finance website.

Write a complete, self-contained, production-ready HTML article about:
  TOPIC: {topic}

═══════════════════════════════════════════════════
ABSOLUTE RULES — never break these
═══════════════════════════════════════════════════
1. Output ONLY valid HTML. Zero markdown, zero explanation, zero code fences.
2. Do NOT rewrite, clean, or reference any other article.
3. Do NOT change nav links, footer links, or canonical URL.
4. Minimum 1200 words of real body content (tables count).
5. Every number, salary figure, and date must be realistic for India in 2026.
6. Do NOT invent government sources; cite well-known public data (7th Pay Commission, EPFO, Income Tax Act, etc.).

═══════════════════════════════════════════════════
SEO REQUIREMENTS
═══════════════════════════════════════════════════
- <title> = exact topic phrase + " | SalaryBit" (60 chars max)
- <meta name="description"> = 150–160 chars, includes primary keyword
- <link rel="canonical" href="{canonical}">
- Open Graph tags: og:title, og:description, og:url, og:image, og:type=article
- Twitter card: summary_large_image
- Schema.org JSON-LD: Article type with headline, datePublished, author, publisher
- Schema.org JSON-LD: FAQPage with 5 Q&A entries (at bottom of <head>)
- One H1 (the article title), then H2 for each major section, H3 for subsections
- Breadcrumb nav: Home → Blog → Article Title
- Alt text on the hero <img>

═══════════════════════════════════════════════════
GOOGLE ADSENSE SLOTS — place EXACTLY these 5 divs
═══════════════════════════════════════════════════
Place these exactly as shown (do not rename classes):

<!-- SLOT 1: below breadcrumb, above H1 (leaderboard) -->
<div class="ad-slot ad-leader" aria-label="Advertisement">
  <ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_PUB_ID}" data-ad-slot="SLOT_LEADER" data-ad-format="auto" data-full-width-responsive="true"></ins>
</div>

<!-- SLOT 2: after intro paragraph (in-article) -->
<div class="ad-slot ad-inarticle" aria-label="Advertisement">
  <ins class="adsbygoogle" style="display:block;text-align:center" data-ad-layout="in-article" data-ad-format="fluid" data-ad-client="{ADSENSE_PUB_ID}" data-ad-slot="SLOT_INARTICLE"></ins>
</div>

<!-- SLOT 3: after the main comparison table (rectangle) -->
<div class="ad-slot ad-rect" aria-label="Advertisement">
  <ins class="adsbygoogle" style="display:inline-block;width:336px;height:280px" data-ad-client="{ADSENSE_PUB_ID}" data-ad-slot="SLOT_RECT"></ins>
</div>

<!-- SLOT 4: before FAQ section (leaderboard) -->
<div class="ad-slot ad-prefaq" aria-label="Advertisement">
  <ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_PUB_ID}" data-ad-slot="SLOT_PREFAQ" data-ad-format="auto" data-full-width-responsive="true"></ins>
</div>

<!-- SLOT 5: sidebar (300×250) inside <aside class="sidebar"> -->
<div class="ad-slot ad-sidebar" aria-label="Advertisement">
  <ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_PUB_ID}" data-ad-slot="SLOT_SIDEBAR" data-ad-format="auto" data-full-width-responsive="true"></ins>
</div>

═══════════════════════════════════════════════════
IMAGE REQUIREMENTS
═══════════════════════════════════════════════════
- Place a hero <img> immediately after the breadcrumb (before slot 1):
    <img src="{og_image}" alt="DESCRIPTIVE ALT TEXT about {topic}" class="hero-img" width="1200" height="630" loading="eager">
- The src path uses the slug-based filename above. Do not change it.

═══════════════════════════════════════════════════
CONTENT STRUCTURE (in this order)
═══════════════════════════════════════════════════
1. Key Takeaways box (3–5 bullet points, class="key-points")
2. Introduction paragraph (150+ words)
3. AD SLOT 2 (in-article)
4. Main salary / data table with realistic 2026 figures
5. AD SLOT 3 (rectangle, centred)
6. 3–4 H2 sections with body text (200+ words each)
7. "Break-even" or decision guide section (where relevant)
8. CTA box linking to https://salarybit.in/#calculator
9. AD SLOT 4 (pre-FAQ)
10. FAQ section: 5 <details>/<summary> pairs (matches JSON-LD FAQPage)
11. Disclaimer line at bottom of article

═══════════════════════════════════════════════════
EXACT CSS + FULL HTML SHELL TO USE
═══════════════════════════════════════════════════
Use this shell verbatim for <head> through <body> open tag and for footer.
Fill in ARTICLE CONTENT HERE with the structured content above.

<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FILL_TITLE | SalaryBit</title>
  <meta name="description" content="FILL_DESCRIPTION">
  <link rel="canonical" href="{canonical}">

  <!-- Open Graph -->
  <meta property="og:title" content="FILL_TITLE">
  <meta property="og:description" content="FILL_DESCRIPTION">
  <meta property="og:url" content="{canonical}">
  <meta property="og:type" content="article">
  <meta property="og:image" content="{og_image}">

  <!-- Twitter -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="FILL_TITLE">
  <meta name="twitter:description" content="FILL_DESCRIPTION">

  <!-- Article Schema -->
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "FILL_TITLE",
    "image": "{og_image}",
    "datePublished": "{today}",
    "dateModified": "{today}",
    "author": {{"@type": "Organization", "name": "SalaryBit"}},
    "publisher": {{"@type": "Organization", "name": "SalaryBit", "url": "{SITE_URL}"}},
    "mainEntityOfPage": "{canonical}"
  }}
  </script>

  <!-- FAQ Schema — fill 5 real Q&A pairs -->
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
      {{"@type":"Question","name":"FAQ_Q1","acceptedAnswer":{{"@type":"Answer","text":"FAQ_A1"}}}},
      {{"@type":"Question","name":"FAQ_Q2","acceptedAnswer":{{"@type":"Answer","text":"FAQ_A2"}}}},
      {{"@type":"Question","name":"FAQ_Q3","acceptedAnswer":{{"@type":"Answer","text":"FAQ_A3"}}}},
      {{"@type":"Question","name":"FAQ_Q4","acceptedAnswer":{{"@type":"Answer","text":"FAQ_A4"}}}},
      {{"@type":"Question","name":"FAQ_Q5","acceptedAnswer":{{"@type":"Answer","text":"FAQ_A5"}}}}
    ]
  }}
  </script>

  <!-- AdSense script -->
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_PUB_ID}" crossorigin="anonymous"></script>

  <!-- Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;0,700;1,400&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">

  <style>
    :root {{
      --saffron:#FF6B00;--saffron-light:#FFF3E8;
      --teal:#138170;--teal-light:#E8F5F2;
      --navy:#0D2137;--navy-mid:#1A3A5C;
      --text:#1C2B3A;--muted:#5A6A7A;
      --border:#E2E8F0;--bg:#FAFBFC;--white:#FFFFFF;
    }}
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'DM Sans',sans-serif;font-size:17px;line-height:1.8;color:var(--text);background:var(--bg)}}

    /* NAV */
    header{{background:var(--navy);position:sticky;top:0;z-index:100;box-shadow:0 2px 12px rgba(0,0,0,.25)}}
    nav{{max-width:1100px;margin:0 auto;display:flex;align-items:center;gap:28px;padding:14px 24px}}
    nav a{{color:#CBD5E1;text-decoration:none;font-size:14px;font-weight:500;transition:color .2s}}
    nav a:hover{{color:var(--white)}}
    nav a.brand{{color:var(--white);font-size:18px;font-weight:700;font-family:'Lora',serif;margin-right:auto}}
    nav a.brand span{{color:var(--saffron)}}

    /* LAYOUT */
    .page-wrap{{max-width:1100px;margin:0 auto;padding:0 24px 60px;display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:40px;align-items:start}}
    article{{min-width:0}}

    /* BREADCRUMB */
    .breadcrumb{{font-size:13px;color:var(--muted);margin:24px 0 16px}}
    .breadcrumb a{{color:var(--teal);text-decoration:none}}
    .breadcrumb a:hover{{text-decoration:underline}}

    /* HERO IMAGE */
    .hero-img{{width:100%;border-radius:12px;display:block;margin-bottom:24px;box-shadow:0 4px 24px rgba(0,0,0,.1)}}

    /* META */
    .article-meta{{display:flex;align-items:center;gap:16px;font-size:13px;color:var(--muted);margin-bottom:20px;flex-wrap:wrap}}
    .badge{{background:var(--saffron-light);color:var(--saffron);font-weight:600;font-size:12px;padding:3px 10px;border-radius:99px}}

    /* HEADINGS */
    h1{{font-family:'Lora',serif;font-size:clamp(1.6rem,4vw,2.2rem);font-weight:700;line-height:1.25;color:var(--navy);margin-bottom:20px}}
    h2{{font-family:'Lora',serif;font-size:1.45rem;font-weight:700;color:var(--navy);margin:44px 0 16px;padding-bottom:10px;border-bottom:2px solid var(--saffron)}}
    h3{{font-size:1.1rem;font-weight:600;color:var(--navy-mid);margin:28px 0 10px}}
    p{{margin-bottom:18px}}
    a{{color:var(--teal)}}
    a:hover{{color:var(--saffron)}}
    ul,ol{{padding-left:22px;margin-bottom:18px}}
    li{{margin-bottom:8px}}

    /* KEY POINTS */
    .key-points{{background:var(--teal-light);border-left:4px solid var(--teal);border-radius:0 8px 8px 0;padding:20px 24px;margin:24px 0}}
    .key-points p{{margin:0 0 6px;font-weight:600;font-size:15px;color:var(--teal)}}
    .key-points ul{{margin-bottom:0;padding-left:20px}}
    .key-points li{{font-size:15px;margin-bottom:6px}}

    /* ALERT */
    .alert{{background:var(--saffron-light);border-left:4px solid var(--saffron);border-radius:0 8px 8px 0;padding:16px 20px;margin:24px 0;font-size:15px}}
    .alert strong{{color:var(--saffron)}}

    /* TABLES */
    .table-wrap{{overflow-x:auto;margin:24px 0}}
    table{{width:100%;border-collapse:collapse;font-size:15px;min-width:480px}}
    thead th{{background:var(--navy);color:var(--white);padding:12px 16px;text-align:left;font-weight:600;font-size:14px;letter-spacing:.03em}}
    tbody tr:nth-child(even){{background:var(--saffron-light)}}
    tbody tr:nth-child(odd){{background:var(--white)}}
    tbody td{{padding:11px 16px;border-bottom:1px solid var(--border)}}
    .highlight-row td{{background:var(--teal-light)!important;font-weight:600;color:var(--teal)}}

    /* CTA */
    .cta-box{{background:linear-gradient(135deg,var(--navy) 0%,var(--navy-mid) 100%);border-radius:12px;padding:32px;text-align:center;margin:40px 0;color:var(--white)}}
    .cta-box h3{{font-family:'Lora',serif;font-size:1.3rem;margin-bottom:8px;color:var(--white);border:none;padding:0;margin-top:0}}
    .cta-box p{{color:#94A3B8;margin-bottom:20px;font-size:15px}}
    .cta-btn{{display:inline-block;background:var(--saffron);color:var(--white);font-weight:700;font-size:15px;padding:13px 32px;border-radius:8px;text-decoration:none;transition:background .2s,transform .15s}}
    .cta-btn:hover{{background:#E05500;color:var(--white);transform:translateY(-1px)}}

    /* AD SLOTS */
    .ad-slot{{margin:32px 0;text-align:center;min-height:50px}}
    .ad-leader{{min-height:90px}}
    .ad-inarticle{{min-height:100px}}
    .ad-rect{{min-height:280px;display:flex;justify-content:center;align-items:center}}
    .ad-prefaq{{min-height:90px}}
    .ad-sidebar{{min-height:250px}}

    /* FAQ */
    .faq-section{{margin-top:48px}}
    details{{border:1px solid var(--border);border-radius:8px;margin-bottom:12px;overflow:hidden}}
    summary{{padding:16px 20px;font-weight:600;font-size:15px;cursor:pointer;color:var(--navy);background:var(--white);display:flex;justify-content:space-between;align-items:center;list-style:none;transition:background .2s}}
    summary:hover{{background:var(--saffron-light)}}
    summary::after{{content:'+';font-size:20px;color:var(--saffron);flex-shrink:0;margin-left:12px}}
    details[open] summary::after{{content:'−'}}
    details[open] summary{{background:var(--saffron-light)}}
    details p{{padding:0 20px 18px;margin:0;font-size:15px;color:var(--muted);line-height:1.7}}

    /* SIDEBAR */
    .sidebar{{position:sticky;top:76px}}
    .sidebar-widget{{background:var(--white);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:24px}}
    .sidebar-widget h4{{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:14px;font-weight:700}}
    .sidebar-widget a{{display:block;font-size:14px;color:var(--navy);text-decoration:none;padding:8px 0;border-bottom:1px solid var(--border);line-height:1.5}}
    .sidebar-widget a:last-child{{border-bottom:none}}
    .sidebar-widget a:hover{{color:var(--saffron)}}

    /* FOOTER */
    footer{{background:var(--navy);color:#64748B;text-align:center;padding:28px 20px;font-size:14px}}
    footer a{{color:#94A3B8;text-decoration:none}}
    footer a:hover{{color:var(--white)}}

    /* RESPONSIVE */
    @media(max-width:860px){{.page-wrap{{grid-template-columns:1fr}}.sidebar{{position:static}}}}
    @media(max-width:480px){{nav{{gap:16px}}nav a:not(.brand):not(:last-child){{display:none}}}}
  </style>
</head>
<body>

<header>
  <nav>
    <a href="{SITE_URL}/index.html" class="brand">Salary<span>Bit</span></a>
    <a href="{SITE_URL}/index.html#calculator">Salary Calculator</a>
    <a href="{SITE_URL}/blog/">Blog</a>
  </nav>
</header>

<div class="page-wrap">
  <article>

    <!-- Breadcrumb -->
    <nav class="breadcrumb" aria-label="Breadcrumb">
      <a href="{SITE_URL}/">Home</a> &rsaquo;
      <a href="{SITE_URL}/blog/">Blog</a> &rsaquo;
      FILL_BREADCRUMB_LABEL
    </nav>

    <!-- Hero Image -->
    <img src="{og_image}" alt="FILL_ALT_TEXT" class="hero-img" width="1200" height="630" loading="eager">

    <!-- AD SLOT 1: Leaderboard (top of article) -->
    <div class="ad-slot ad-leader" aria-label="Advertisement">
      <ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_PUB_ID}" data-ad-slot="SLOT_LEADER" data-ad-format="auto" data-full-width-responsive="true"></ins>
    </div>

    <!-- Article meta -->
    <div class="article-meta">
      <span class="badge">FILL_CATEGORY</span>
      <span>Updated {today}</span>
      <span>&#128337; FILL_READ_TIME min read</span>
    </div>

    <h1>FILL_H1</h1>

    <!-- Key takeaways -->
    FILL_KEY_POINTS_BOX

    <!-- Introduction -->
    FILL_INTRO_PARAGRAPHS

    <!-- AD SLOT 2: In-article (after intro) -->
    <div class="ad-slot ad-inarticle" aria-label="Advertisement">
      <ins class="adsbygoogle" style="display:block;text-align:center" data-ad-layout="in-article" data-ad-format="fluid" data-ad-client="{ADSENSE_PUB_ID}" data-ad-slot="SLOT_INARTICLE"></ins>
    </div>

    <!-- Main content sections -->
    FILL_MAIN_CONTENT

    <!-- AD SLOT 3: Rectangle (after main table) -->
    <div class="ad-slot ad-rect" aria-label="Advertisement">
      <ins class="adsbygoogle" style="display:inline-block;width:336px;height:280px" data-ad-client="{ADSENSE_PUB_ID}" data-ad-slot="SLOT_RECT"></ins>
    </div>

    <!-- More content sections -->
    FILL_SECONDARY_CONTENT

    <!-- CTA -->
    <div class="cta-box">
      <h3>&#128200; Calculate Your Exact In-Hand Salary</h3>
      <p>Use SalaryBit's free calculator — enter your CTC and get your take-home pay in seconds.</p>
      <a href="{SITE_URL}/#calculator" class="cta-btn">Try the Free Calculator &#8594;</a>
    </div>

    <!-- AD SLOT 4: Before FAQ -->
    <div class="ad-slot ad-prefaq" aria-label="Advertisement">
      <ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_PUB_ID}" data-ad-slot="SLOT_PREFAQ" data-ad-format="auto" data-full-width-responsive="true"></ins>
    </div>

    <!-- FAQ Section -->
    <section class="faq-section">
      <h2>Frequently Asked Questions</h2>
      FILL_FAQ_DETAILS
    </section>

    <p style="font-size:13px;color:var(--muted);margin-top:32px">
      <em>Disclaimer: Salary figures are approximate and based on publicly available data. Actual salaries may vary by company, location, and experience. This article is for informational purposes only.</em>
    </p>

  </article>

  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="sidebar-widget">
      <!-- AD SLOT 5: Sidebar -->
      <div class="ad-slot ad-sidebar" aria-label="Advertisement">
        <ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_PUB_ID}" data-ad-slot="SLOT_SIDEBAR" data-ad-format="auto" data-full-width-responsive="true"></ins>
      </div>
    </div>

    <div class="sidebar-widget">
      <h4>&#128218; Related Articles</h4>
      <a href="{SITE_URL}/blog/article2-old-vs-new-tax-regime.html">Old vs New Tax Regime FY 2026-27</a>
      <a href="{SITE_URL}/blog/">HRA Exemption Calculator Guide</a>
      <a href="{SITE_URL}/blog/">Section 80C Investments Explained</a>
      <a href="{SITE_URL}/blog/">EPF vs PPF: Which is Better?</a>
    </div>

    <div class="sidebar-widget">
      <h4>&#128200; Free Tools</h4>
      <a href="{SITE_URL}/#calculator">&#8594; In-Hand Salary Calculator</a>
      <a href="{SITE_URL}/#calculator">&#8594; Tax Regime Comparison</a>
    </div>
  </aside>
</div>

<footer>
  <p>&copy; 2026 <a href="{SITE_URL}/">SalaryBit.in</a> &nbsp;|&nbsp;
     <a href="{SITE_URL}/index.html">Home</a> &nbsp;|&nbsp;
     <a href="{SITE_URL}/blog/">Blog</a> &nbsp;|&nbsp;
     <a href="{SITE_URL}/#calculator">Salary Calculator</a></p>
  <p style="margin-top:8px;font-size:12px;">
    Disclaimer: Information on this site is for educational purposes only. Consult a financial advisor for personalised advice.
  </p>
</footer>

<script>
  (adsbygoogle = window.adsbygoogle || []).push({{}});
</script>

</body>
</html>

═══════════════════════════════════════════════════
NOW WRITE THE FULL ARTICLE
═══════════════════════════════════════════════════
Replace every FILL_* placeholder with real content about "{topic}".
- Use real 2026 Indian salary data.
- All tables must have at least 4 rows of real data.
- FAQ must have exactly 5 <details>/<summary> pairs.
- The JSON-LD FAQ must match the <details> FAQ.
- Do NOT add any extra <style> blocks or change the CSS.
- Output only the complete HTML document, nothing else.
Today's date: {today}
"""

# ── Core: write one article ────────────────────────────────────────────────────
def write_article(topic: str) -> tuple[str, str]:
    slug    = make_slug(topic)
    today   = datetime.now().strftime("%B %d, %Y")
    iso     = datetime.now().strftime("%Y-%m-%d")

    print(f"  Writing: {topic}")
    prompt = build_prompt(topic, slug, today)
    html   = call_groq(prompt, max_tokens=6000)
    html   = strip_markdown_fences(html)

    # Sanity check: must start with <!DOCTYPE
    if not html.strip().lower().startswith("<!doctype"):
        raise ValueError(f"Model did not return valid HTML for topic: {topic}")

    os.makedirs(BLOG_FOLDER, exist_ok=True)
    filepath = os.path.join(BLOG_FOLDER, f"{slug}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Saved  → {filepath}")
    return topic, f"{slug}.html"

# ── Blog index update ─────────────────────────────────────────────────────────
def update_blog_index(topic: str, filename: str):
    if not os.path.exists(BLOG_INDEX_PATH):
        print(f"  ⚠  {BLOG_INDEX_PATH} not found — skipping index update.")
        print(f"     Add <!-- NEW-ARTICLES --> comment to blog/index.html to enable auto-update.")
        return

    with open(BLOG_INDEX_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    marker = "<!-- NEW-ARTICLES -->"
    if marker not in content:
        print(f"  ⚠  Marker '{marker}' not in blog/index.html — skipping index update.")
        return

    month = datetime.now().strftime("%B %Y")
    card  = f"""<a href="{SITE_URL}/blog/{filename}">
        <div class="article-card">
            <h3>{topic}</h3>
            <span>{month}</span>
        </div>
    </a>"""
    content = content.replace(marker, f"{marker}\n    {card}")

    with open(BLOG_INDEX_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Blog index updated.")

# ── Sitemap ───────────────────────────────────────────────────────────────────
def update_sitemap():
    articles = [
        f for f in os.listdir(BLOG_FOLDER)
        if f.endswith(".html") and f != "index.html"
    ] if os.path.exists(BLOG_FOLDER) else []

    today  = datetime.now().strftime("%Y-%m-%d")
    urls   = [f"<url><loc>{SITE_URL}/</loc><priority>1.0</priority></url>"]
    for a in sorted(articles):
        urls.append(
            f"<url><loc>{SITE_URL}/blog/{a}</loc>"
            f"<lastmod>{today}</lastmod><priority>0.8</priority></url>"
        )

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )
    with open(SITEMAP_PATH, "w") as f:
        f.write(sitemap)
    print(f"  Sitemap updated ({len(articles)} articles).")

# ── Main runner ───────────────────────────────────────────────────────────────
def run_agent(write_all: bool = False):
    published = load_json(PUBLISHED_FILE, [])
    remaining = [t for t in NEW_TOPICS if t not in published]

    if not remaining:
        print("✅ All topics already published! Reset published_topics.json to restart.")
        return

    topics_to_write = remaining if write_all else [remaining[0]]

    for i, topic in enumerate(topics_to_write):
        print(f"\n[{i+1}/{len(topics_to_write)}] {topic}")
        try:
            topic_name, filename = write_article(topic)
            update_blog_index(topic_name, filename)
            published.append(topic)
            save_json(PUBLISHED_FILE, published)
            if write_all and i < len(topics_to_write) - 1:
                print("  Waiting 15s before next article...")
                time.sleep(15)
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            continue

    update_sitemap()
    print("\n✅ Done!")

if __name__ == "__main__":
    write_all = "--all" in sys.argv
    print(f"SalaryBit Agent | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)
    print("Mode:", "Write ALL remaining articles" if write_all else "Write ONE article")
    print("=" * 50)
    run_agent(write_all=write_all)
