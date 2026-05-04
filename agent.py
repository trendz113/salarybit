from groq import Groq
import os
import time
import json
import math
from datetime import datetime

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

BLOG_FOLDER = "blog"
PUBLISHED_FILE = "published_topics.json"

# ── Replace with your real AdSense publisher ID when approved ──────────────
ADSENSE_CLIENT      = "ca-pub-XXXXXXXXXXXXXXXXX"  # e.g. ca-pub-1234567890123456
ADSENSE_SLOT_TOP    = "1111111111"
ADSENSE_SLOT_BOTTOM = "3333333333"
# ───────────────────────────────────────────────────────────────────────────

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

# ── Unsplash keyword map ───────────────────────────────────────────────────
UNSPLASH_KEYWORD_MAP = {
    "software":   "software-developer-laptop",
    "engineer":   "engineering-technology",
    "doctor":     "doctor-hospital-india",
    "teacher":    "classroom-india",
    "nurse":      "nurse-hospital",
    "army":       "indian-army",
    "police":     "police-india",
    "bank":       "bank-finance-india",
    "ias":        "government-office-india",
    "mba":        "business-graduate",
    "ca ":        "accountant-finance",
    "hra":        "house-rent-apartment",
    "pf ":        "savings-india",
    "epf":        "retirement-savings",
    "tax":        "income-tax-india",
    "pan":        "document-identity-india",
    "gratuity":   "employee-benefits",
    "layoff":     "career-transition",
    "data":       "data-analytics",
    "salary":     "office-work-india",
}

def get_unsplash_image_url(topic):
    topic_lower = topic.lower()
    keyword = "india,office,work"
    for key, val in UNSPLASH_KEYWORD_MAP.items():
        if key in topic_lower:
            keyword = val
            break
    return f"https://source.unsplash.com/1200x600/?{keyword}"

def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def make_slug(topic):
    slug = topic.lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    return slug[:60]

def estimate_read_time(html_body):
    words = len(html_body.split())
    return max(1, math.ceil(words / 200))

def call_groq(prompt, max_tokens=1500):
    for attempt in range(5):
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            err = str(e)
            print(f"Attempt {attempt+1} failed: {err}")
            if "rate_limit_exceeded" in err or "413" in err:
                wait = 60 * (attempt + 1)
                print(f"Rate limit hit. Waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                time.sleep(15)
    raise Exception("Failed after 5 attempts. Aborting.")

def build_adsense_script():
    if "XXXXXXXXX" in ADSENSE_CLIENT:
        return "<!-- AdSense: set your ADSENSE_CLIENT publisher ID in agent.py to enable -->"
    return f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CLIENT}" crossorigin="anonymous"></script>'

def build_adsense_block(slot_id):
    if "XXXXXXXXX" in ADSENSE_CLIENT:
        return '<div class="ad-slot"><span class="ad-label">Advertisement</span></div>'
    return f"""<div class="ad-slot">
  <span class="ad-label">Advertisement</span>
  <ins class="adsbygoogle"
       style="display:block"
       data-ad-client="{ADSENSE_CLIENT}"
       data-ad-slot="{slot_id}"
       data-ad-format="auto"
       data-full-width-responsive="true"></ins>
  <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
</div>"""

# ── Self-contained CSS ─────────────────────────────────────────────────────
ARTICLE_CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{font-size:16px;scroll-behavior:smooth}
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:#f8f9fa;color:#1a1a2e;line-height:1.7}
a{color:#0066cc;text-decoration:none}
a:hover{text-decoration:underline}

/* Header */
header{background:#0f3460;padding:14px 24px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.2)}
header a{color:#fff;font-size:1.3rem;font-weight:700;letter-spacing:.5px}

/* Hero */
.hero-image{width:100%;max-height:380px;object-fit:cover;display:block}

/* Layout */
.article-wrap{max-width:820px;margin:0 auto;padding:0 16px 48px}

/* Meta */
.article-meta{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:20px 0 8px;font-size:.85rem;color:#666}
.article-meta .badge{background:#e8f0fe;color:#0f3460;padding:3px 10px;border-radius:20px;font-weight:600;font-size:.78rem}

/* Headings */
h1{font-size:clamp(1.5rem,4vw,2rem);color:#0f3460;line-height:1.3;margin:12px 0 20px}
h2{font-size:1.35rem;color:#0f3460;margin:36px 0 12px;padding-bottom:6px;border-bottom:2px solid #e0e7ff}
h3{font-size:1.1rem;color:#1a1a2e;margin:24px 0 8px}
p{margin-bottom:16px}
ul,ol{margin:0 0 16px 24px}
li{margin-bottom:6px}

/* Table */
.salary-table-wrap{overflow-x:auto;margin:24px 0}
table{width:100%;border-collapse:collapse;font-size:.92rem}
thead{background:#0f3460;color:#fff}
th,td{padding:11px 14px;text-align:left;border:1px solid #dde3f0}
tbody tr:nth-child(even){background:#f0f4ff}
tbody tr:hover{background:#dce8ff}

/* FAQ */
.faq-section{margin-top:40px}
.faq-section h2{border-color:#ffd700}
.faq-item{background:#fff;border:1px solid #e0e7ff;border-radius:10px;margin-bottom:14px;overflow:hidden}
.faq-question{width:100%;background:none;border:none;padding:16px 20px;text-align:left;font-size:.97rem;font-weight:600;color:#0f3460;cursor:pointer;display:flex;justify-content:space-between;align-items:center}
.faq-question::after{content:"+";font-size:1.4rem;color:#0066cc}
.faq-question.open::after{content:"−"}
.faq-answer{display:none;padding:0 20px 16px;font-size:.93rem;color:#444}
.faq-answer.open{display:block}

/* Ad Slot */
.ad-slot{background:#f0f4ff;border:1px dashed #b0bce0;border-radius:8px;padding:20px;text-align:center;margin:28px 0;min-height:90px;display:flex;flex-direction:column;align-items:center;justify-content:center}
.ad-label{font-size:.7rem;color:#999;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;display:block}

/* Footer */
footer{background:#0f3460;color:#ccd6f6;text-align:center;padding:20px;font-size:.85rem;margin-top:48px}
footer a{color:#7ec8e3}

/* Mobile */
@media(max-width:600px){
  h1{font-size:1.4rem}
  th,td{padding:8px 10px;font-size:.85rem}
  .article-meta{font-size:.8rem}
}
"""

FAQ_JS = """<script>
document.querySelectorAll('.faq-question').forEach(btn => {
  btn.addEventListener('click', () => {
    btn.classList.toggle('open');
    btn.nextElementSibling.classList.toggle('open');
  });
});
</script>"""

def write_new_article():
    published = load_json(PUBLISHED_FILE, [])
    topic = None
    for t in NEW_TOPICS:
        if t not in published:
            topic = t
            break
    if not topic:
        published = []
        save_json(PUBLISHED_FILE, published)
        topic = NEW_TOPICS[0]

    slug     = make_slug(topic)
    filename = f"{slug}.html"
    print(f"Writing: {topic}")

    # ── Call 1: Article body (1200 tokens) ────────────────────────────────
    body_prompt = f"""Write an HTML article body about: {topic}
For Indian readers on salarybit.in. Date: {datetime.now().strftime('%B %Y')}.

Requirements:
- 600-700 words, accurate for India
- Real salary numbers
- One HTML salary comparison table wrapped in <div class="salary-table-wrap">
- Use H2 and H3 only (no H1)
- FAQ section at the end using EXACTLY this structure:
  <div class="faq-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <button class="faq-question">Question?</button>
      <div class="faq-answer"><p>Answer.</p></div>
    </div>
  </div>
- NO doctype, NO head, NO html/body tags
- Output valid HTML only, no markdown, no explanation"""

    body_html = call_groq(body_prompt, max_tokens=1200)
    time.sleep(15)

    # ── Call 2: SEO meta (120 tokens) ─────────────────────────────────────
    meta_prompt = f"""For an article about "{topic}" on an Indian salary website:
TITLE: (max 60 chars, include 2026)
DESC: (max 155 chars, mention India and key numbers)
Output only those two lines."""

    meta_raw  = call_groq(meta_prompt, max_tokens=120)
    seo_title = topic
    seo_desc  = f"Find accurate {topic} data with tables and real numbers for India."
    for line in meta_raw.splitlines():
        if line.startswith("TITLE:"):
            seo_title = line.replace("TITLE:", "").strip()
        elif line.startswith("DESC:"):
            seo_desc = line.replace("DESC:", "").strip()

    # ── Supporting values ──────────────────────────────────────────────────
    image_url   = get_unsplash_image_url(topic)
    read_time   = estimate_read_time(body_html)
    pub_date    = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+05:30")
    pub_display = datetime.now().strftime("%B %d, %Y")

    schema_json = f"""{{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "{seo_title}",
  "description": "{seo_desc}",
  "image": "{image_url}",
  "datePublished": "{pub_date}",
  "dateModified": "{pub_date}",
  "author": {{
    "@type": "Organization",
    "name": "SalaryBit",
    "url": "https://salarybit.in"
  }},
  "publisher": {{
    "@type": "Organization",
    "name": "SalaryBit",
    "logo": {{
      "@type": "ImageObject",
      "url": "https://salarybit.in/logo.png"
    }}
  }},
  "mainEntityOfPage": {{
    "@type": "WebPage",
    "@id": "https://salarybit.in/blog/{filename}"
  }}
}}"""

    # ── Assemble full HTML ─────────────────────────────────────────────────
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{seo_title} | SalaryBit</title>
  <meta name="description" content="{seo_desc}">
  <link rel="canonical" href="https://salarybit.in/blog/{filename}">

  <!-- Schema.org structured data (helps Google show rich results) -->
  <script type="application/ld+json">
  {schema_json}
  </script>

  <!-- Google AdSense (activates automatically once publisher ID is set) -->
  {build_adsense_script()}

  <style>{ARTICLE_CSS}</style>
</head>
<body>

<header>
  <a href="../index.html">SalaryBit</a>
</header>

<!-- Hero Image via Unsplash (free, no API key needed) -->
<img
  class="hero-image"
  src="{image_url}"
  alt="{seo_title}"
  loading="eager"
  width="1200"
  height="600"
/>

<div class="article-wrap">

  <!-- Article meta: category badge, date, read time -->
  <div class="article-meta">
    <span class="badge">Salary Guide</span>
    <span>📅 {pub_display}</span>
    <span>⏱ {read_time} min read</span>
  </div>

  <h1>{seo_title}</h1>

  <!-- Ad Slot 1: Below H1 — highest viewability position -->
  {build_adsense_block(ADSENSE_SLOT_TOP)}

  <!-- Article Body (generated by Groq) -->
  {body_html}

  <!-- Ad Slot 2: End of content — good for engaged readers -->
  {build_adsense_block(ADSENSE_SLOT_BOTTOM)}

</div>

<footer>
  <p>&copy; 2026 SalaryBit.in &nbsp;|&nbsp;
     <a href="../index.html">Home</a> &nbsp;|&nbsp;
     <a href="../blog/index.html">All Articles</a>
  </p>
</footer>

{FAQ_JS}
</body>
</html>"""

    os.makedirs(BLOG_FOLDER, exist_ok=True)
    with open(f"{BLOG_FOLDER}/{filename}", "w", encoding="utf-8") as f:
        f.write(full_html)

    published.append(topic)
    save_json(PUBLISHED_FILE, published)
    print(f"Saved: {filename}")
    return seo_title, filename, image_url, pub_display

def update_blog_index(title, filename, image_url, pub_display):
    filepath = "blog/index.html"
    if not os.path.exists(filepath):
        print("WARNING: blog/index.html not found!")
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    if "<!-- NEW-ARTICLES -->" not in content:
        print("WARNING: Add <!-- NEW-ARTICLES --> placeholder to blog/index.html!")
        return
    new_card = f"""<a href="https://salarybit.in/blog/{filename}" class="article-card">
      <img src="{image_url}" alt="{title}" loading="lazy" width="400" height="200">
      <div class="card-body">
        <h3>{title}</h3>
        <span>{pub_display}</span>
      </div>
    </a>"""
    content = content.replace(
        "<!-- NEW-ARTICLES -->",
        f"<!-- NEW-ARTICLES -->\n    {new_card}"
    )
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Blog index updated: {title}")

def update_sitemap():
    articles = []
    if os.path.exists(BLOG_FOLDER):
        for f in os.listdir(BLOG_FOLDER):
            if f.endswith(".html") and f != "index.html":
                articles.append(f)
    today = datetime.now().strftime("%Y-%m-%d")
    urls  = [
        "<url><loc>https://salarybit.in/</loc><priority>1.0</priority></url>",
        "<url><loc>https://salarybit.in/blog/</loc><priority>0.9</priority></url>",
    ]
    for a in sorted(articles):
        urls.append(
            f"<url><loc>https://salarybit.in/blog/{a}</loc>"
            f"<lastmod>{today}</lastmod>"
            f"<priority>0.8</priority></url>"
        )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n</urlset>"
    )
    with open("sitemap.xml", "w") as f:
        f.write(sitemap)
    print("Sitemap updated!")

def run_agent():
    print(f"SalaryBit Agent | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 48)
    print("Mode: Write ONE article")
    print("=" * 48)
    try:
        title, filename, image_url, pub_display = write_new_article()
        update_blog_index(title, filename, image_url, pub_display)
        update_sitemap()
        print("=" * 48)
        print(f"Done! Article: {filename}")
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        raise SystemExit(1)

if __name__ == "__main__":
    run_agent()
