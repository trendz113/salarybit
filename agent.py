from groq import Groq
import os
import time
import json
from datetime import datetime

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

BLOG_FOLDER = "blog"
PROCESSED_FILE = "processed_articles.json"
PUBLISHED_FILE = "published_topics.json"

# FIX 1: FILES_TO_CLEAN was missing — caused NameError crash in clean_existing_article()
FILES_TO_CLEAN = [
    "pan-complete.html",
    "layoff-survival-guide.html",
    "subscription-manager.html",
    "karnataka_dl_renewal_guide.html",
]

NEW_TOPICS = [
    
    "EPF withdrawal process India 2026",
    "Gratuity calculation formula India",
]

# Shared <head> block injected into every article
def make_head(title, description, canonical_url):
    return f"""  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | SalaryBit</title>
  <meta name="description" content="{description}">
  <link rel="canonical" href="{canonical_url}">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='%235b6af0'/><text y='22' x='5' font-size='18'>💰</text></svg>">
  <link rel="stylesheet" href="../style.css">
  <!-- Google AdSense -->
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-8336334158316485" crossorigin="anonymous"></script>
  <!-- Google Analytics -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-QFHT4BZTMF"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-QFHT4BZTMF');</script>"""

ARTICLE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
{head}
</head>
<body>
<header>
  <a href="/index.html">SalaryBit</a>
  <nav>
    <a href="/index.html">Calculator</a>
    <a href="/blog/">Blog</a>
  </nav>
</header>
<main class="article-container">
  <div class="ad-slot"><!-- Ad --></div>
  {content}
  <div class="ad-slot"><!-- Ad --></div>
  {faq}
  <div class="cta-strip">
    <h3>Calculate Your Exact Salary</h3>
    <p>Use SalaryBit's free calculator to see your in-hand salary, compare tax regimes, and plan smarter.</p>
    <a href="/index.html">Open Calculator →</a>
  </div>
</main>
<footer>
  <p>© 2026 SalaryBit · <a href="/index.html">Home</a> · <a href="/blog/">Blog</a></p>
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
    prompt = f"""You are an SEO content writer for salarybit.in — an Indian salary and finance website.

Rewrite this article as clean HTML content. Follow ALL rules strictly:

RULES:
1. DO NOT include any <img> tags — no images at all
2. DO NOT include <html>, <head>, <body>, <header>, <footer>, <script> or <style> tags — only the inner article content
3. DO NOT include any personal data (names, phone numbers, Aadhaar, PAN, bank accounts)
4. Output ONLY the article body HTML — starting with <div class="breadcrumb"> and ending with the last </section> or </div>
5. Use H1 once, then H2 and H3 for subheadings
6. Include at least one salary comparison table with proper <table><thead><tbody> structure
7. Write 1000+ words useful for Indian salaried readers
8. End with a FAQ section using this structure:
<section class="faq-section">
  <h2>Frequently Asked Questions</h2>
  <div class="faq-item"><h3>Question?</h3><p>Answer.</p></div>
  <div class="faq-item"><h3>Question?</h3><p>Answer.</p></div>
  <div class="faq-item"><h3>Question?</h3><p>Answer.</p></div>
</section>

Start with:
<div class="breadcrumb"><a href="/index.html">Home</a> › <a href="/blog/">Blog</a> › Article Title</div>
<div class="article-meta"><span class="tag">CATEGORY</span><span>Updated {datetime.now().strftime('%B %Y')}</span><span>8 min read</span></div>
<h1>Article Title</h1>

Here is the existing article to rewrite:
{html_content}"""
    content = call_groq(prompt)
    # Strip any accidental markdown code fences
    content = content.replace("```html", "").replace("```", "").strip()
    # Build full page using template
    canonical = f"https://salarybit.in/blog/{article_to_clean}"
    title_line = article_to_clean.replace("-", " ").replace(".html", "").title()
    head = make_head(title_line, f"Complete guide to {title_line} for Indian professionals.", canonical)
    full_html = ARTICLE_TEMPLATE.format(head=head, content=content, faq="")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_html)
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
    prompt = f"""You are an SEO content writer for salarybit.in — an Indian salary and finance website.

Write a complete article about: {topic}

RULES — follow ALL strictly:
1. DO NOT include any <img> tags — no images at all
2. DO NOT include <html>, <head>, <body>, <header>, <footer>, <script> or <style> tags — only article body HTML
3. Output ONLY the inner article HTML — starting with <div class="breadcrumb"> and ending after the FAQ section
4. Use H1 once at the top, then H2 and H3 for subheadings
5. Include at least one salary table with <table><thead><tbody> — real Indian salary numbers in rupees
6. Write 1000+ words, simple English, useful for Indian salaried readers
7. End with a FAQ section:
<section class="faq-section">
  <h2>Frequently Asked Questions</h2>
  <div class="faq-item"><h3>Question?</h3><p>Answer.</p></div>
  <div class="faq-item"><h3>Question?</h3><p>Answer.</p></div>
  <div class="faq-item"><h3>Question?</h3><p>Answer.</p></div>
</section>

Start output with:
<div class="breadcrumb"><a href="/index.html">Home</a> › <a href="/blog/">Blog</a> › {topic}</div>
<div class="article-meta"><span class="tag">Salary Guide</span><span>Updated {datetime.now().strftime('%B %Y')}</span><span>8 min read</span></div>
<h1>{topic}</h1>

Today's date: {datetime.now().strftime('%B %d, %Y')}"""

    content = call_groq(prompt)
    # Strip any accidental markdown code fences
    content = content.replace("```html", "").replace("```", "").strip()
    slug = make_slug(topic)
    filename = f"{slug}.html"
    canonical = f"https://salarybit.in/blog/{filename}"
    head = make_head(topic, f"Complete guide to {topic}. Real salary data, tables and tips for Indian professionals.", canonical)
    full_html = ARTICLE_TEMPLATE.format(head=head, content=content, faq="")
    os.makedirs(BLOG_FOLDER, exist_ok=True)
    with open(f"{BLOG_FOLDER}/{filename}", "w", encoding="utf-8") as f:
        f.write(full_html)
    published.append(topic)
    save_json(PUBLISHED_FILE, published)
    print(f"Saved: {filename}")
    return topic, filename

def pick_emoji(topic):
    t = topic.lower()
    if any(w in t for w in ["tax", "income", "slab", "itr"]):
        return "📋"
    elif any(w in t for w in ["pf", "epf", "provident", "gratuity"]):
        return "🏦"
    elif any(w in t for w in ["hra", "house", "rent"]):
        return "🏠"
    elif any(w in t for w in ["negotiat", "hike", "appraisal"]):
        return "🤝"
    elif any(w in t for w in ["layoff", "termination", "resignation", "compensation"]):
        return "🛟"
    elif any(w in t for w in ["doctor", "nurse", "health"]):
        return "🏥"
    elif any(w in t for w in ["pan", "aadhaar", "document"]):
        return "🪪"
    elif any(w in t for w in ["engineer", "software", "developer", "data"]):
        return "💻"
    elif any(w in t for w in ["government", "ias", "army", "police", "teacher"]):
        return "🏛️"
    elif any(w in t for w in ["bank", "po", "finance"]):
        return "🏦"
    elif any(w in t for w in ["mba", "ca", "fresher"]):
        return "🎓"
    return "💰"

# FIX 2: Card format updated to match the new blog/index.html structure.
# Old format wrapped <div class="article-card"> inside <a href="...">, which
# broke hover styles and didn't inherit .article-card CSS from the index.
# New format uses <a class="article-card" href="..."> — matching existing cards.
# Also switched from absolute URLs (https://salarybit.in/blog/...) to root-relative (/blog/...).
def update_blog_index(topic, filename):
    filepath = "blog/index.html"
    if not os.path.exists(filepath):
        print("blog/index.html not found!")
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    emoji = pick_emoji(topic)
    new_card = f"""<a class="article-card" href="/blog/{filename}">
      <div class="emoji">{emoji}</div>
      <div class="category">Salary Guide</div>
      <h2>{topic}</h2>
      <p>Complete guide to {topic.lower()} — with real salary data, tables and expert tips for Indian professionals.</p>
      <div class="meta"><span>8 min read</span><span class="read-link">Read Guide →</span></div>
    </a>"""

    if "<!-- NEW-ARTICLES -->" in content:
        content = content.replace("<!-- NEW-ARTICLES -->", f"<!-- NEW-ARTICLES -->\n\n    {new_card}")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Blog index updated: {topic}")
    else:
        print("WARNING: <!-- NEW-ARTICLES --> comment missing from blog/index.html!")

def update_sitemap():
    articles = []
    if os.path.exists(BLOG_FOLDER):
        for f in os.listdir(BLOG_FOLDER):
            if f.endswith(".html") and f != "index.html":
                articles.append(f)
    urls = ["<url><loc>https://salarybit.in/</loc><priority>1.0</priority></url>"]
    for a in sorted(articles):
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
