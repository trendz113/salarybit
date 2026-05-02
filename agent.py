from groq import Groq
import os
import time
import json
from datetime import datetime

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

BLOG_FOLDER = "blog"
PROCESSED_FILE = "processed_articles.json"
PUBLISHED_FILE = "published_topics.json"

FILES_TO_CLEAN = [
    "pan-complete.html",
    "layoff-survival-guide.html",
    "subscription-manager.html",
    "karnataka_dl_renewal_guide.html",
]

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

# ─────────────────────────────────────────────
# SalaryBit styled HTML template — injected into every article
# ─────────────────────────────────────────────
STYLE_BLOCK = """<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet"/>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --navy: #0e2a47; --navy2: #163755; --accent: #f07d3a; --accent2: #ffa05c;
      --text: #1a1a2e; --muted: #5e6e82; --bg: #f4f6f9; --card: #ffffff; --border: #dde3ec;
    }
    body { font-family: 'DM Sans', sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; }
    nav { background: var(--navy); padding: 18px 40px; display: flex; align-items: center; justify-content: space-between; }
    .logo { font-family: 'Playfair Display', serif; color: #fff; font-size: 1.5rem; font-weight: 800; text-decoration: none; }
    .logo span { color: var(--accent); }
    nav a.nl { color: rgba(255,255,255,.75); text-decoration: none; font-size: .88rem; font-weight: 500; margin-left: 28px; }
    nav a.nl:hover { color: #fff; }
    .hero { background: linear-gradient(145deg, var(--navy) 0%, #1a4a7a 60%, #1e5a8e 100%); padding: 72px 40px 80px; text-align: center; position: relative; overflow: hidden; }
    .hero::before { content: ''; position: absolute; inset: 0; background: radial-gradient(ellipse 80% 60% at 50% 120%, rgba(240,125,58,.18), transparent); }
    .hero-tag { display: inline-block; background: var(--accent); color: #fff; font-size: .72rem; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; padding: 6px 18px; border-radius: 50px; margin-bottom: 24px; }
    .hero h1 { font-family: 'Playfair Display', serif; font-size: clamp(1.8rem, 4vw, 2.8rem); font-weight: 800; color: #fff; line-height: 1.25; max-width: 760px; margin: 0 auto 20px; }
    .hero-meta { color: rgba(255,255,255,.55); font-size: .85rem; display: flex; gap: 18px; justify-content: center; align-items: center; }
    .sw { max-width: 860px; margin: -48px auto 0; padding: 0 24px; position: relative; z-index: 10; }
    .sg { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
    .sc { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 28px 20px 24px; text-align: center; box-shadow: 0 4px 24px rgba(14,42,71,.10); }
    .sc .val { font-family: 'Playfair Display', serif; font-size: 2.1rem; font-weight: 800; color: var(--navy); line-height: 1; margin-bottom: 10px; }
    .sc .lbl { font-size: .8rem; color: var(--muted); font-weight: 500; line-height: 1.4; }
    .aw { max-width: 740px; margin: 60px auto 80px; padding: 0 24px; }
    .aw h2 { font-family: 'Playfair Display', serif; font-size: 1.65rem; font-weight: 800; color: var(--navy); margin: 48px 0 16px; line-height: 1.3; }
    .aw h3 { font-size: 1.05rem; font-weight: 700; color: var(--navy); margin: 32px 0 10px; }
    .aw p { font-size: 1.01rem; color: #2c3e55; margin-bottom: 18px; }
    .aw ul, .aw ol { padding-left: 22px; margin-bottom: 18px; }
    .aw ul li, .aw ol li { font-size: 1rem; color: #2c3e55; margin-bottom: 8px; }
    .tw { overflow-x: auto; margin: 28px 0 40px; border-radius: 14px; border: 1px solid var(--border); box-shadow: 0 2px 12px rgba(14,42,71,.07); }
    table { width: 100%; border-collapse: collapse; font-size: .93rem; }
    thead tr { background: var(--navy); color: #fff; }
    thead th { padding: 14px 18px; text-align: left; font-weight: 600; font-size: .82rem; letter-spacing: .5px; text-transform: uppercase; }
    tbody tr { border-bottom: 1px solid var(--border); transition: background .15s; }
    tbody tr:last-child { border-bottom: none; }
    tbody tr:hover { background: #f0f5fb; }
    tbody td { padding: 13px 18px; color: var(--text); }
    tbody td:first-child { font-weight: 600; color: var(--navy); }
    .callout { background: #eef5ff; border-left: 4px solid var(--navy); border-radius: 0 12px 12px 0; padding: 20px 24px; margin: 32px 0; font-size: .97rem; color: var(--navy2); }
    .callout strong { display: block; margin-bottom: 4px; }
    .faq-item { margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid var(--border); }
    .faq-item:last-child { border-bottom: none; }
    .faq-q { font-weight: 700; color: var(--navy); margin-bottom: 6px; font-size: 1rem; }
    .faq-a { color: #2c3e55; font-size: .97rem; }
    footer { background: var(--navy); color: rgba(255,255,255,.5); text-align: center; padding: 32px 20px; font-size: .82rem; }
    footer a { color: var(--accent2); text-decoration: none; }
    @media(max-width:600px) { nav { padding: 16px 20px; } .hero { padding: 56px 20px 72px; } .sg { grid-template-columns: 1fr; } .sw { margin-top: -24px; } }
  </style>"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>TITLE | SalaryBit</title>
  <meta name="description" content="DESCRIPTION"/>
  <link rel="canonical" href="https://salarybit.in/blog/SLUG.html"/>
  {STYLE_BLOCK}
</head>
<body>

<nav>
  <a class="logo" href="../index.html">Salary<span>Bit</span></a>
  <div>
    <a class="nl" href="../index.html">Home</a>
    <a class="nl" href="../index.html#guides">Guides</a>
  </div>
</nav>

<section class="hero">
  <div class="hero-tag">CATEGORY_TAG</div>
  <h1>ARTICLE TITLE HERE</h1>
  <div class="hero-meta">
    <span>Updated MONTH YEAR</span>
    <span>·</span>
    <span>X min read</span>
  </div>
</section>

<div class="sw">
  <div class="sg">
    <div class="sc"><div class="val">STAT1</div><div class="lbl">Label 1</div></div>
    <div class="sc"><div class="val">STAT2</div><div class="lbl">Label 2</div></div>
    <div class="sc"><div class="val">STAT3</div><div class="lbl">Label 3</div></div>
  </div>
</div>

<div class="aw">

  <p>INTRO PARAGRAPH</p>

  <h2>Section Heading</h2>
  <p>Content here.</p>

  <div class="tw">
    <table>
      <thead><tr><th>Column 1</th><th>Column 2</th><th>Column 3</th></tr></thead>
      <tbody>
        <tr><td>Row 1</td><td>Value</td><td>Value</td></tr>
      </tbody>
    </table>
  </div>

  <div class="callout">
    <strong>Pro Tip</strong>
    Useful tip relevant to the article topic.
  </div>

  <h2>FAQs</h2>
  <div class="faq-item">
    <div class="faq-q">Question 1?</div>
    <div class="faq-a">Answer 1.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q">Question 2?</div>
    <div class="faq-a">Answer 2.</div>
  </div>
  <div class="faq-item">
    <div class="faq-q">Question 3?</div>
    <div class="faq-a">Answer 3.</div>
  </div>

</div>

<footer>
  &copy; 2026 SalaryBit.in &nbsp;|&nbsp; <a href="../index.html">Home</a>
</footer>

</body>
</html>"""


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

def call_groq(prompt):
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(30)
    raise Exception("Failed after 3 attempts")

def clean_existing_article():
    processed = load_json(PROCESSED_FILE, [])
    article_to_clean = None
    for f in FILES_TO_CLEAN:
        if f not in processed:
            article_to_clean = f
            break
    if not article_to_clean:
        print("All articles already cleaned!")
        return
    filepath = f"{BLOG_FOLDER}/{article_to_clean}"
    if not os.path.exists(filepath):
        print(f"File not found: {article_to_clean}")
        processed.append(article_to_clean)
        save_json(PROCESSED_FILE, processed)
        return
    print(f"Cleaning: {article_to_clean}")
    with open(filepath, "r", encoding="utf-8") as f:
        html_content = f.read()
    html_content = html_content[:6000]

    prompt = f"""You are a web developer for salarybit.in — an Indian salary and finance website.

Rewrite this article using the EXACT HTML template below. Do not change the template structure or styles at all.
Output ONLY valid HTML. No markdown, no backticks, no explanation.

RULES:
1. REMOVE all personal details (names, phone numbers, emails, Aadhaar, PAN, bank accounts).
2. Keep all useful content — salary tables, lists, explanations.
3. Make it ~1000 words useful for Indian readers.
4. Fill in the 3 stat cards (.sc) with real key numbers from the article.
5. Set CATEGORY_TAG to the correct category (e.g. Salary Guide, Tax Guide, Government Jobs).
6. Wrap every <table> inside <div class="tw">...</div>.
7. Convert any FAQ section into <div class="faq-item"> blocks.
8. Add one <div class="callout"> with a useful pro tip.
9. Set correct title, meta description, canonical URL for: {article_to_clean}

USE THIS EXACT TEMPLATE (keep all CSS and structure intact):

{HTML_TEMPLATE.replace("{STYLE_BLOCK}", STYLE_BLOCK)}

Here is the existing article content to rewrite:
{html_content}"""

    improved = call_groq(prompt)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(improved)
    processed.append(article_to_clean)
    save_json(PROCESSED_FILE, processed)
    print(f"Cleaned: {article_to_clean}")

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
    print(f"Writing: {topic}")
    slug = make_slug(topic)

    prompt = f"""You are a professional blog writer for salarybit.in — an Indian salary and finance website.

Write a complete, accurate, SEO-optimised article about: "{topic}"

Output ONLY valid HTML. No markdown, no backticks, no explanation.

RULES:
1. ~1000 words with real salary numbers useful for Indian readers.
2. Fill the 3 stat cards (.sc .val) with the 3 most important numbers from the article.
3. Set CATEGORY_TAG appropriately (e.g. Salary Guide, Tax Guide, Government Jobs, Career Guide).
4. Wrap every <table> inside <div class="tw">...</div>.
5. Include at least one salary comparison table with a navy thead.
6. Add one <div class="callout"> with a useful pro tip.
7. Add 3 FAQ items as <div class="faq-item"> blocks at the end.
8. Set correct title, meta description, and canonical URL slug: {slug}.html
9. Set the hero H1 to a clear, compelling article title.
10. DO NOT use <link rel="stylesheet" href="../style.css"> — all styles are already in the template.

USE THIS EXACT TEMPLATE (keep all CSS and structure intact, just fill in the content):

{HTML_TEMPLATE.replace("{STYLE_BLOCK}", STYLE_BLOCK)}

Today's date: {datetime.now().strftime('%B %d, %Y')}"""

    html = call_groq(prompt)
    filename = f"{slug}.html"
    os.makedirs(BLOG_FOLDER, exist_ok=True)
    with open(f"{BLOG_FOLDER}/{filename}", "w", encoding="utf-8") as f:
        f.write(html)
    published.append(topic)
    save_json(PUBLISHED_FILE, published)
    print(f"Saved: {filename}")
    return topic, filename

def update_blog_index(title, filename):
    filepath = "blog/index.html"
    if not os.path.exists(filepath):
        print("blog/index.html not found!")
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    new_card = f"""<a href="https://salarybit.in/blog/{filename}">
        <div class="article-card">
            <h3>{title}</h3>
            <span>{datetime.now().strftime('%B %Y')}</span>
        </div>
    </a>"""
    if "<!-- NEW-ARTICLES -->" in content:
        content = content.replace("<!-- NEW-ARTICLES -->", f"<!-- NEW-ARTICLES -->\n    {new_card}")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Blog index updated: {title}")
    else:
        print("Add <!-- NEW-ARTICLES --> comment to blog/index.html!")

def update_sitemap():
    articles = []
    if os.path.exists(BLOG_FOLDER):
        for f in os.listdir(BLOG_FOLDER):
            if f.endswith(".html") and f != "index.html":
                articles.append(f)
    urls = ["<url><loc>https://salarybit.in/</loc><priority>1.0</priority></url>"]
    for a in articles:
        urls.append(f"<url><loc>https://salarybit.in/blog/{a}</loc><lastmod>{datetime.now().strftime('%Y-%m-%d')}</lastmod><priority>0.8</priority></url>")
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"
    with open("sitemap.xml", "w") as f:
        f.write(sitemap)
    print("Sitemap updated!")

def run_agent():
    print(f"SalaryBit Agent | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 40)
    print("TASK 1: Cleaning existing article...")
    clean_existing_article()
    time.sleep(10)
    print("TASK 2: Writing new article...")
    topic, filename = write_new_article()
    print("TASK 3: Updating blog index...")
    update_blog_index(topic, filename)
    update_sitemap()
    print("=" * 40)
    print("Done!")

if __name__ == "__main__":
    run_agent()
