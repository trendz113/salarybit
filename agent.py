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

def call_groq(prompt, max_tokens=1500):
    """Call Groq with retry logic and rate limit handling."""
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
                wait = 60 * (attempt + 1)  # 60s, 120s, 180s ...
                print(f"Rate limit hit. Waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                time.sleep(15)
    raise Exception("Failed after 5 attempts. Aborting.")

def write_new_article():
    published = load_json(PUBLISHED_FILE, [])
    topic = None
    for t in NEW_TOPICS:
        if t not in published:
            topic = t
            break
    if not topic:
        # All topics done, reset and start again
        published = []
        save_json(PUBLISHED_FILE, published)
        topic = NEW_TOPICS[0]

    slug = make_slug(topic)
    filename = f"{slug}.html"
    print(f"Writing: {topic}")

    # --- Part 1: Generate article body (lean prompt, 1200 tokens) ---
    body_prompt = f"""Write HTML article body about: {topic}
For Indian readers on salarybit.in. Date: {datetime.now().strftime('%B %Y')}.

Requirements:
- 600-700 words
- Real salary numbers for India
- One salary comparison table (HTML table)
- Use H2 and H3 headings only (no H1 here)
- FAQ section at end with 3 questions and answers
- NO doctype, NO head, NO body tags - only the inner content

Start directly with the article content."""

    body_html = call_groq(body_prompt, max_tokens=1200)
    time.sleep(15)  # pause between calls to avoid TPM limits

    # --- Part 2: Generate meta info (tiny prompt, 150 tokens) ---
    meta_prompt = f"""For an article about "{topic}" on an Indian salary website, give me ONLY:
1. SEO title (max 60 chars)
2. Meta description (max 155 chars)

Format exactly:
TITLE: ...
DESC: ..."""

    meta_raw = call_groq(meta_prompt, max_tokens=150)

    # Parse title and description
    seo_title = topic  # fallback
    seo_desc = f"Find out about {topic} with accurate data for India."
    for line in meta_raw.splitlines():
        if line.startswith("TITLE:"):
            seo_title = line.replace("TITLE:", "").strip()
        elif line.startswith("DESC:"):
            seo_desc = line.replace("DESC:", "").strip()

    # --- Assemble full HTML ---
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{seo_title} | SalaryBit</title>
  <meta name="description" content="{seo_desc}">
  <link rel="canonical" href="https://salarybit.in/blog/{filename}">
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <header><a href="../index.html"><h2>SalaryBit</h2></a></header>
  <main class="article-container">
    <h1>{seo_title}</h1>
    <div class="ad-slot"><!-- Ad --></div>
    {body_html}
    <div class="ad-slot"><!-- Ad --></div>
  </main>
  <footer><p>2026 SalaryBit.in | <a href="../index.html">Home</a></p></footer>
</body>
</html>"""

    os.makedirs(BLOG_FOLDER, exist_ok=True)
    with open(f"{BLOG_FOLDER}/{filename}", "w", encoding="utf-8") as f:
        f.write(full_html)

    published.append(topic)
    save_json(PUBLISHED_FILE, published)
    print(f"Saved: {filename}")
    return seo_title, filename

def update_blog_index(title, filename):
    filepath = "blog/index.html"
    if not os.path.exists(filepath):
        print("WARNING: blog/index.html not found! Add <!-- NEW-ARTICLES --> placeholder to it.")
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    if "<!-- NEW-ARTICLES -->" not in content:
        print("WARNING: <!-- NEW-ARTICLES --> comment missing from blog/index.html! Please add it.")
        return
    new_card = f"""<a href="https://salarybit.in/blog/{filename}">
        <div class="article-card">
            <h3>{title}</h3>
            <span>{datetime.now().strftime('%B %Y')}</span>
        </div>
    </a>"""
    content = content.replace("<!-- NEW-ARTICLES -->", f"<!-- NEW-ARTICLES -->\n    {new_card}")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Blog index updated: {title}")

def update_sitemap():
    articles = []
    if os.path.exists(BLOG_FOLDER):
        for f in os.listdir(BLOG_FOLDER):
            if f.endswith(".html") and f != "index.html":
                articles.append(f)
    urls = ["<url><loc>https://salarybit.in/</loc><priority>1.0</priority></url>"]
    for a in sorted(articles):
        urls.append(
            f"<url><loc>https://salarybit.in/blog/{a}</loc>"
            f"<lastmod>{datetime.now().strftime('%Y-%m-%d')}</lastmod>"
            f"<priority>0.8</priority></url>"
        )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
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
        topic, filename = write_new_article()
        update_blog_index(topic, filename)
        update_sitemap()
        print("=" * 48)
        print(f"Done! Article: {filename}")
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        raise SystemExit(1)  # non-zero exit so GitHub Actions marks it FAILED

if __name__ == "__main__":
    run_agent()
