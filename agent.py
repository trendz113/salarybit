import google.generativeai as genai
import os
import time
import json
from datetime import datetime

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash-preview-04-17")

BLOG_FOLDER = "blog"
PROCESSED_FILE = "processed_articles.json"
PUBLISHED_FILE = "published_topics.json"

NEW_TOPICS = [
    "TCS software engineer salary in India 2025",
    "Infosys fresher salary package 2025",
    "Government teacher salary India state wise",
    "IAS officer salary and perks India",
    "Data scientist salary in India 2025",
    "Bank PO salary after 7th pay commission",
    "Amazon India software developer salary",
    "Doctor salary government hospital India",
    "MBA fresher salary in India 2025",
    "CA salary in India after articleship",
    "HRA calculation formula India",
    "PF deduction calculation guide India",
    "Income tax slab 2025-26 India",
    "How to calculate take home salary India",
    "Average salary in India by profession 2025",
    "Nurse salary India government vs private",
    "Army soldier salary in India 2025",
    "Police constable salary state wise India",
    "Software engineer salary Hyderabad vs Bangalore",
    "Wipro salary hike 2025",
    "Layoff compensation India 2025",
    "PAN card apply online India guide",
    "Duplicate PAN card application process",
    "EPF withdrawal process India 2025",
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

def call_gemini(prompt):
    for attempt in range(3):
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(60)
    raise Exception("Failed after 3 attempts")

# ===== TASK 1 — IMPROVE EXISTING ARTICLE =====
def get_all_articles():
    articles = []
    if os.path.exists(BLOG_FOLDER):
        for f in os.listdir(BLOG_FOLDER):
            if f.endswith(".html") and f != "index.html":
                articles.append(f)
    return articles

def improve_existing_article():
    processed = load_json(PROCESSED_FILE, [])
    all_articles = get_all_articles()

    # Pick one unprocessed article
    article_to_process = None
    for article in all_articles:
        if article not in processed:
            article_to_process = article
            break

    if not article_to_process:
        print("All articles improved! Resetting...")
        processed = []
        save_json(PROCESSED_FILE, processed)
        article_to_process = all_articles[0] if all_articles else None

    if not article_to_process:
        print("No articles found!")
        return

    print(f"Improving existing: {article_to_process}")

    with open(f"{BLOG_FOLDER}/{article_to_process}", "r", encoding="utf-8") as f:
        html_content = f.read()

    prompt = f"""You are an SEO expert for salarybit.in — Indian salary and finance website.

Improve this existing HTML article:

1. REMOVE all personal details:
   - Real names, phone numbers, email addresses
   - Home addresses, Aadhaar numbers
   - Real PAN card numbers of individuals
   - Any private personal information

2. IMPROVE the content:
   - Make it 1000-1500 words
   - Add proper SEO title and meta description
   - Add salary/finance tables where relevant
   - Add FAQ section at end (3-5 questions)
   - Fix headings (H1 once, then H2/H3)
   - Add <div class='ad-slot'><!-- Ad --></div> at top, middle, bottom
   - Write for Indian readers

3. Use this HTML structure:
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TITLE | SalaryBit</title>
  <meta name="description" content="DESCRIPTION">
  <link rel="canonical" href="https://salarybit.in/blog/{article_to_process}">
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <header><a href="../index.html"><h2>💰 SalaryBit</h2></a></header>
  <main class="article-container">
    <div class="ad-slot"><!-- Ad --></div>
    IMPROVED CONTENT HERE
    <div class="ad-slot"><!-- Ad --></div>
    FAQ HERE
    <div class="ad-slot"><!-- Ad --></div>
  </main>
  <footer><p>© 2025 SalaryBit.in | <a href="../index.html">Home</a></p></footer>
</body>
</html>

Output ONLY valid HTML — no markdown, no explanation.

Existing article:
{html_content}"""

    improved = call_gemini(prompt)

    with open(f"{BLOG_FOLDER}/{article_to_process}", "w", encoding="utf-8") as f:
        f.write(improved)

    processed.append(article_to_process)
    save_json(PROCESSED_FILE, processed)
    print(f"✅ Improved: {article_to_process}")

# ===== TASK 2 — WRITE NEW ARTICLE =====
def write_new_article():
    published = load_json(PUBLISHED_FILE, [])

    # Pick unpublished topic
    topic = None
    for t in NEW_TOPICS:
        if t not in published:
            topic = t
            break

    if not topic:
        print("All topics published! Resetting...")
        published = []
        save_json(PUBLISHED_FILE, published)
        topic = NEW_TOPICS[0]

    print(f"Writing new article: {topic}")

    prompt = f"""Write a complete SEO HTML article for salarybit.in about: {topic}

Rules:
- 1000-1500 words, useful for Indian readers
- Real salary/finance numbers and tables
- Output ONLY valid HTML, no markdown
- Proper title and meta description
- H1 once, then H2/H3 headings
- Salary comparison table
- FAQ section at end (3-5 questions)
- Add <div class='ad-slot'><!-- Ad --></div> at top, middle, bottom

HTML structure:
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TITLE | SalaryBit</title>
  <meta name="description" content="DESCRIPTION">
  <link rel="canonical" href="https://salarybit.in/blog/SLUG.html">
  <link rel="stylesheet" href="../style.css">
</head>
<body>
  <header><a href="../index.html"><h2>💰 SalaryBit</h2></a></header>
  <main class="article-container">
    <div class="ad-slot"><!-- Ad --></div>
    ARTICLE CONTENT
    <div class="ad-slot"><!-- Ad --></div>
    FAQ
    <div class="ad-slot"><!-- Ad --></div>
  </main>
  <footer><p>© 2025 SalaryBit.in | <a href="../index.html">Home</a></p></footer>
</body>
</html>

Today's date: {datetime.now().strftime('%B %d, %Y')}"""

    html = call_gemini(prompt)

    slug = make_slug(topic)
    filename = f"{slug}.html"
    os.makedirs(BLOG_FOLDER, exist_ok=True)

    with open(f"{BLOG_FOLDER}/{filename}", "w", encoding="utf-8") as f:
        f.write(html)

    published.append(topic)
    save_json(PUBLISHED_FILE, published)
    print(f"✅ New article: {filename}")

# ===== UPDATE SITEMAP =====
def update_sitemap():
    articles = get_all_articles()
    urls = ['<url><loc>https://salarybit.in/</loc><priority>1.0</priority></url>']
    for a in articles:
        urls.append(f'<url><loc>https://salarybit.in/blog/{a}</loc><lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod><priority>0.8</priority></url>')
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"
    with open("sitemap.xml", "w") as f:
        f.write(sitemap)
    print("✅ Sitemap updated!")

# ===== MAIN =====
def run_agent():
    print(f"🤖 SalaryBit Agent | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 40)

    # Task 1 — Improve existing article
    print("📝 TASK 1: Improving existing article...")
    improve_existing_article()
    time.sleep(30)  # Wait 30 seconds between API calls

    # Task 2 — Write new article
    print("✍️  TASK 2: Writing new article...")
    write_new_article()

    # Update sitemap
    update_sitemap()

    print("=" * 40)
    print("🎉 Both tasks done! Netlify will deploy shortly.")

if __name__ == "__main__":
    run_agent()
