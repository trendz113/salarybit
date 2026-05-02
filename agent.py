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

# Internal calculator links to inject into articles
CALCULATOR_LINKS = {
    "salary": "https://salarybit.in/#calculator",
    "tax": "https://salarybit.in/#tax-regime",
    "hra": "https://salarybit.in/#calculator",
    "pf": "https://salarybit.in/#epf",
    "gratuity": "https://salarybit.in/#gratuity",
    "emi": "https://salarybit.in/#home-loan",
    "sip": "https://salarybit.in/#sip",
    "epf": "https://salarybit.in/#epf",
}

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

def call_groq(prompt, max_tokens=6000):
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                # upgraded model: much better quality, still free on Groq
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(30)
    raise Exception("Failed after 3 attempts")

def build_article_prompt(topic, slug):
    today = datetime.now().strftime("%B %d, %Y")
    return f"""You are an expert Indian finance and salary writer for salarybit.in.

Write a COMPLETE, LONG, HIGH-QUALITY SEO article about: "{topic}"

STRICT REQUIREMENTS:
1. Minimum 1800 words of body content. Do not stop early.
2. Use REAL, ACCURATE salary data from sources like Glassdoor, AmbitionBox, LinkedIn, PayScale India. Cite the source name inline (e.g. "According to AmbitionBox...").
3. Write naturally for Indian salaried employees — simple English, relatable examples.
4. Include ALL of these sections:
   - Introduction (150 words) — hook the reader with a real problem or question
   - Salary overview table (experience-wise: 0-2 yrs, 2-5 yrs, 5-10 yrs, 10+ yrs)
   - City-wise salary comparison table (at least 5 cities)
   - Company-wise salary table (at least 5 companies with real data)
   - Factors that affect salary (skills, certifications, location) — at least 300 words
   - How to increase your salary — practical tips — at least 200 words
   - CTA paragraph linking to SalaryBit calculator
   - FAQ section with 5 real questions and detailed answers

5. Add this internal link naturally in the article body:
   <a href="https://salarybit.in/#calculator">calculate your exact in-hand salary on SalaryBit</a>

6. Add JSON-LD schema for FAQPage at the bottom of <head>.

7. Use this EXACT HTML structure — output ONLY valid HTML, no markdown, no explanation:

<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>[KEYWORD-RICH TITLE] | SalaryBit</title>
  <meta name="description" content="[155 char description with keyword and year]">
  <link rel="canonical" href="https://salarybit.in/blog/{slug}.html">
  <link rel="stylesheet" href="../style.css">
  <meta property="og:title" content="[TITLE]">
  <meta property="og:description" content="[DESCRIPTION]">
  <meta property="og:url" content="https://salarybit.in/blog/{slug}.html">
  <meta property="og:type" content="article">
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
      {{
        "@type": "Question",
        "name": "[FAQ Q1]",
        "acceptedAnswer": {{"@type": "Answer", "text": "[FAQ A1]"}}
      }},
      {{
        "@type": "Question",
        "name": "[FAQ Q2]",
        "acceptedAnswer": {{"@type": "Answer", "text": "[FAQ A2]"}}
      }},
      {{
        "@type": "Question",
        "name": "[FAQ Q3]",
        "acceptedAnswer": {{"@type": "Answer", "text": "[FAQ A3]"}}
      }},
      {{
        "@type": "Question",
        "name": "[FAQ Q4]",
        "acceptedAnswer": {{"@type": "Answer", "text": "[FAQ A4]"}}
      }},
      {{
        "@type": "Question",
        "name": "[FAQ Q5]",
        "acceptedAnswer": {{"@type": "Answer", "text": "[FAQ A5]"}}
      }}
    ]
  }}
  </script>
</head>
<body>
  <header>
    <nav>
      <a href="https://salarybit.in/index.html"><strong>SalaryBit</strong></a>
      <a href="https://salarybit.in/index.html#calculator">Salary Calculator</a>
      <a href="https://salarybit.in/blog/">Blog</a>
    </nav>
  </header>
  <main class="article-container">
    <article>
      <div class="article-meta">
        <span>Updated {today}</span>
        <span>10 min read</span>
      </div>
      <div class="ad-slot"><!-- Ad --></div>

      [FULL ARTICLE CONTENT HERE — MINIMUM 1800 WORDS]

      <div class="ad-slot"><!-- Ad --></div>

      <div class="calculator-cta">
        <h3>Calculate Your In-Hand Salary</h3>
        <p>Use SalaryBit's free salary calculator to find your exact take-home pay after tax, PF and all deductions.</p>
        <a href="https://salarybit.in/#calculator" class="cta-button">Calculate Now — Free</a>
      </div>

      <div class="ad-slot"><!-- Ad --></div>

      <section class="faq-section">
        <h2>Frequently Asked Questions</h2>
        [5 FAQ ITEMS HERE as <details><summary>Q</summary><p>A</p></details>]
      </section>

    </article>
  </main>
  <footer>
    <p>&copy; 2026 SalaryBit.in | <a href="https://salarybit.in/index.html">Home</a> | <a href="https://salarybit.in/blog/">Blog</a></p>
  </footer>
</body>
</html>

Today's date: {today}
Topic: {topic}
"""

def build_clean_prompt(article_to_clean, html_content):
    today = datetime.now().strftime("%B %d, %Y")
    slug = article_to_clean.replace(".html", "")
    return f"""You are an expert Indian finance writer and SEO specialist for salarybit.in.

Rewrite and GREATLY IMPROVE this existing article. The current version is too short and weak.

STRICT REQUIREMENTS:
1. Minimum 1800 words of body content.
2. REMOVE ALL personal details — names, phone numbers, emails, Aadhaar, PAN, bank accounts.
3. Use REAL salary/finance data. Cite sources like AmbitionBox, Glassdoor, PayScale inline.
4. Write simply for Indian salaried employees.
5. Add ALL these sections:
   - Strong introduction (150 words)
   - Data tables (salary by experience, city, company where relevant)
   - Factors affecting the topic — at least 300 words
   - Practical tips section — at least 200 words
   - Internal link to SalaryBit calculator: <a href="https://salarybit.in/#calculator">calculate your in-hand salary</a>
   - FAQ with 5 questions and detailed answers
6. Add FAQPage JSON-LD schema in <head>.
7. Output ONLY valid HTML, no markdown, no explanation.

Use this HTML structure:
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>[TITLE] | SalaryBit</title>
  <meta name="description" content="[155 char SEO description]">
  <link rel="canonical" href="https://salarybit.in/blog/{slug}.html">
  <link rel="stylesheet" href="../style.css">
  <meta property="og:title" content="[TITLE]">
  <meta property="og:description" content="[DESCRIPTION]">
  <meta property="og:url" content="https://salarybit.in/blog/{slug}.html">
  <meta property="og:type" content="article">
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
      {{"@type":"Question","name":"[Q1]","acceptedAnswer":{{"@type":"Answer","text":"[A1]"}}}},
      {{"@type":"Question","name":"[Q2]","acceptedAnswer":{{"@type":"Answer","text":"[A2]"}}}},
      {{"@type":"Question","name":"[Q3]","acceptedAnswer":{{"@type":"Answer","text":"[A3]"}}}},
      {{"@type":"Question","name":"[Q4]","acceptedAnswer":{{"@type":"Answer","text":"[A4]"}}}},
      {{"@type":"Question","name":"[Q5]","acceptedAnswer":{{"@type":"Answer","text":"[A5]"}}}}
    ]
  }}
  </script>
</head>
<body>
  <header>
    <nav>
      <a href="https://salarybit.in/index.html"><strong>SalaryBit</strong></a>
      <a href="https://salarybit.in/index.html#calculator">Salary Calculator</a>
      <a href="https://salarybit.in/blog/">Blog</a>
    </nav>
  </header>
  <main class="article-container">
    <article>
      <div class="article-meta">
        <span>Updated {today}</span>
        <span>10 min read</span>
      </div>
      <div class="ad-slot"><!-- Ad --></div>
      [FULL REWRITTEN ARTICLE — MINIMUM 1800 WORDS]
      <div class="ad-slot"><!-- Ad --></div>
      <div class="calculator-cta">
        <h3>Calculate Your In-Hand Salary</h3>
        <p>Use SalaryBit's free calculator to find your exact take-home pay.</p>
        <a href="https://salarybit.in/#calculator" class="cta-button">Calculate Now — Free</a>
      </div>
      <div class="ad-slot"><!-- Ad --></div>
      <section class="faq-section">
        <h2>Frequently Asked Questions</h2>
        [5 FAQ as <details><summary>Q</summary><p>A</p></details>]
      </section>
    </article>
  </main>
  <footer>
    <p>&copy; 2026 SalaryBit.in | <a href="https://salarybit.in/index.html">Home</a> | <a href="https://salarybit.in/blog/">Blog</a></p>
  </footer>
</body>
</html>

Existing article to rewrite:
{html_content}
"""

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
    # increased context window — send more of the original article
    html_content = html_content[:10000]
    prompt = build_clean_prompt(article_to_clean, html_content)
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
    prompt = build_article_prompt(topic, slug)
    html = call_groq(prompt)
    filename = f"{slug}.html"
    os.makedirs(BLOG_FOLDER, exist_ok=True)
    with open(f"{BLOG_FOLDER}/{filename}", "w", encoding="utf-8") as f:
        f.write(html)
    published.append(topic)
    save_json(PUBLISHED_FILE, published)
    print(f"Saved: {filename}")
    return topic, filename

def extract_title_from_html(html):
    """Extract title from generated HTML for blog index."""
    import re
    match = re.search(r"<title>(.*?)\s*\|\s*SalaryBit</title>", html, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def update_blog_index(topic, filename):
    filepath = "blog/index.html"
    if not os.path.exists(filepath):
        print("blog/index.html not found!")
        return
    # Try to read actual generated title from the file
    article_path = f"{BLOG_FOLDER}/{filename}"
    display_title = topic
    if os.path.exists(article_path):
        with open(article_path, "r", encoding="utf-8") as f:
            content = f.read()
        extracted = extract_title_from_html(content)
        if extracted:
            display_title = extracted
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    new_card = f"""<a href="https://salarybit.in/blog/{filename}">
        <div class="article-card">
            <h3>{display_title}</h3>
            <span>{datetime.now().strftime('%B %Y')}</span>
        </div>
    </a>"""
    if "<!-- NEW-ARTICLES -->" in content:
        content = content.replace("<!-- NEW-ARTICLES -->", f"<!-- NEW-ARTICLES -->\n    {new_card}")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Blog index updated: {display_title}")
    else:
        print("WARNING: Add <!-- NEW-ARTICLES --> comment to blog/index.html!")

def update_sitemap():
    articles = []
    if os.path.exists(BLOG_FOLDER):
        for f in sorted(os.listdir(BLOG_FOLDER)):
            if f.endswith(".html") and f != "index.html":
                articles.append(f)
    today = datetime.now().strftime("%Y-%m-%d")
    urls = [
        "<url><loc>https://salarybit.in/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>",
        "<url><loc>https://salarybit.in/blog/</loc><changefreq>daily</changefreq><priority>0.9</priority></url>",
    ]
    for a in articles:
        urls.append(
            f"<url><loc>https://salarybit.in/blog/{a}</loc>"
            f"<lastmod>{today}</lastmod>"
            f"<changefreq>monthly</changefreq>"
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
    print(f"Sitemap updated with {len(articles)} articles!")

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
