import google.generativeai as genai
import os
import time
import json
from datetime import datetime

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

TOPICS = [
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
]

def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def pick_topic(published):
    for t in TOPICS:
        if t not in published:
            return t
    return TOPICS[0]

def make_slug(topic):
    slug = topic.lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    return slug[:60]

def generate_article(topic):
    print(f"Writing: {topic}")
    prompt = f"""Write a complete SEO HTML article for salarybit.in about: {topic}

Rules:
- 1000-1500 words, useful content for Indian readers
- Real salary numbers and tables
- Output ONLY valid HTML, no markdown, no explanation
- Proper title and meta description for SEO
- H1 once, then H2/H3 headings
- Include salary comparison table
- End with FAQ section 3-5 questions
- Add <div class='ad-slot'><!-- Ad --></div> at top, middle, bottom

Use this HTML structure:
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
  <header><a href="../index.html"><h2>SalaryBit</h2></a></header>
  <main class="article-container">
    <div class="ad-slot"><!-- Ad --></div>
    ARTICLE CONTENT HERE
    <div class="ad-slot"><!-- Ad --></div>
    FAQ SECTION HERE
    <div class="ad-slot"><!-- Ad --></div>
  </main>
  <footer><p>2025 SalaryBit.in | <a href="../index.html">Home</a></p></footer>
</body>
</html>

Today's date: {datetime.now().strftime('%B %d, %Y')}"""

    for attempt in range(3):
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(60)
    raise Exception("Failed after 3 attempts")

def update_sitemap(articles):
    urls = ['<url><loc>https://salarybit.in/</loc><priority>1.0</priority></url>']
    for a in articles:
        urls.append(f'<url><loc>https://salarybit.in/blog/{a["filename"]}</loc><lastmod>{a["date"]}</lastmod><priority>0.8</priority></url>')
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"
    with open("sitemap.xml", "w") as f:
        f.write(sitemap)
    print("Sitemap updated!")

def run_agent():
    print(f"SalaryBit Agent | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    published = load_json("published_topics.json", [])
    articles = load_json("articles_list.json", [])
    topic = pick_topic(published)
    html = generate_article(topic)
    slug = make_slug(topic)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{slug}.html"
    os.makedirs("blog", exist_ok=True)
    with open(f"blog/{filename}", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved: blog/{filename}")
    published.append(topic)
    articles.append({"title": topic, "filename": filename, "date": date_str})
    save_json("published_topics.json", published)
    save_json("articles_list.json", articles)
    update_sitemap(articles)
    print(f"Done: https://salarybit.in/blog/{filename}")

if __name__ == "__main__":
    run_agent()
