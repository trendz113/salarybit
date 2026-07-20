#!/usr/bin/env python3
"""
Auto-updates index.html (homepage blog section) and blog/index.html
whenever a new blog/*.html file is added.

SAFE BY DESIGN: this script never rewrites or removes existing cards.
It only detects blog posts that don't yet have a card, and appends a
new card for each one at the top of the grid. Your hand-edited cards
are never touched.

How it finds post metadata (in order of priority):
  1. Custom meta tags in the post's <head>, if you add them:
       <meta name="blog:emoji" content="🏦">
       <meta name="blog:category" content="Insurance · Family Finance">
       <meta name="blog:readtime" content="9 min read">
  2. Falls back to the post's <title> and <meta name="description">.
  3. Falls back to sensible defaults (📄 / "Guide" / estimated read time).

Run manually:   python3 scripts/generate_blog_index.py
Run via CI:     see .github/workflows/update-blog-index.yml
"""

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BLOG_DIR = REPO_ROOT / "blog"
HOMEPAGE = REPO_ROOT / "index.html"
BLOG_INDEX = BLOG_DIR / "index.html"

EMOJI_KEYWORDS = {
    "insurance": "👪", "tax": "🧾", "salary": "💰", "loan": "🏦",
    "emi": "🏠", "gratuity": "🏆", "pf": "🏦", "epf": "🏦",
    "labour": "⚖️", "layoff": "⚖️", "credit card": "💳",
    "gold": "🥇", "property": "🏘️", "khata": "📄", "driving": "🚗",
    "job": "💼", "ai": "🤖", "subscription": "🔍", "pan": "🪪",
}
DEFAULT_EMOJI = "📄"
DEFAULT_CATEGORY = "Guide"


def extract_meta(html: str, name: str) -> str | None:
    m = re.search(
        rf'<meta\s+name=["\']{re.escape(name)}["\']\s+content=["\'](.*?)["\']',
        html, re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def extract_title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not m:
        return "Untitled Post"
    title = re.sub(r"\s+", " ", m.group(1)).strip()
    # strip common suffixes like " | SalaryBit"
    title = re.split(r"\s*[|\u2014]\s*SalaryBit", title, flags=re.IGNORECASE)[0]
    return title.strip()


def estimate_readtime(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    words = len(re.findall(r"\w+", text))
    minutes = max(2, round(words / 200))
    return f"{minutes} min read"


def guess_emoji(title: str, category: str) -> str:
    haystack = f"{title} {category}".lower()
    for kw, emoji in EMOJI_KEYWORDS.items():
        if kw in haystack:
            return emoji
    return DEFAULT_EMOJI


def git_created_date(filepath: Path) -> str:
    """Returns the date the file was first committed, or today's date."""
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--follow", "--format=%aI", "--", str(filepath)],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        if out:
            return out.splitlines()[-1][:10]
    except Exception:
        pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def existing_hrefs(html: str) -> set[str]:
    return set(re.findall(r'href="(/blog/[a-zA-Z0-9\-_]+\.html)"', html))


def build_post_meta(filepath: Path) -> dict:
    html = filepath.read_text(encoding="utf-8", errors="ignore")
    title = extract_meta(html, "og:title") or extract_title(html)
    description = extract_meta(html, "description") or ""
    category = extract_meta(html, "blog:category") or DEFAULT_CATEGORY
    emoji = extract_meta(html, "blog:emoji") or guess_emoji(title, category)
    readtime = extract_meta(html, "blog:readtime") or estimate_readtime(html)
    date = git_created_date(filepath)
    is_new = (datetime.now(timezone.utc).date() - datetime.strptime(date, "%Y-%m-%d").date()).days <= 30
    return {
        "slug": filepath.name,
        "title": title,
        "description": description[:220],
        "category": category,
        "emoji": emoji,
        "readtime": readtime,
        "date": date,
        "is_new": is_new,
        "month_label": datetime.strptime(date, "%Y-%m-%d").strftime("%B %Y").upper(),
    }


def homepage_card(post: dict) -> str:
    new_badge = (
        '\n        <div style="display:inline-flex;align-items:center;gap:4px;'
        'background:var(--accent-bg);border:1px solid var(--accent-border);color:var(--accent);'
        'font-size:9px;font-weight:700;padding:2px 7px;border-radius:10px;margin-bottom:.4rem">🆕 NEW</div>'
        if post["is_new"] else ""
    )
    return f'''      <a class="article-card" href="/blog/{post['slug']}">
        <div class="article-tag">{post['emoji']} {post['category']}</div>{new_badge}
        <h2>{post['title']}</h2>
        <p>{post['description']}</p>
        <div class="article-meta">
          <span>{post['date'][:4]} · {post['readtime']}</span>
          <span class="read-link">Read →</span>
        </div>
      </a>
'''


def blog_index_card(post: dict) -> str:
    badge = (
        f'\n      <div style="position:absolute;top:-10px;left:16px;background:#16a34a;color:#fff;'
        f'font-size:10px;font-weight:700;padding:2px 10px;border-radius:10px;letter-spacing:.06em">'
        f'🆕 NEW — {post["month_label"]}</div>'
        if post["is_new"] else ""
    )
    style = ' style="border:2px solid #16a34a;position:relative"' if post["is_new"] else ""
    return f'''    <a class="article-card" href="/blog/{post['slug']}"{style}>{badge}
      <div class="emoji">{post['emoji']}</div>
      <div class="category">{post['category']}</div>
      <h2>{post['title']}</h2>
      <p>{post['description']}</p>
      <div class="meta"><span>{post['readtime']}</span><span class="read-link">Read Guide →</span></div>
    </a>
'''


def insert_after(html: str, anchor: str, insertion: str) -> str:
    idx = html.find(anchor)
    if idx == -1:
        raise RuntimeError(f"Anchor not found: {anchor!r}")
    idx += len(anchor)
    return html[:idx] + "\n" + insertion + html[idx:]


def update_homepage(new_posts: list[dict]) -> bool:
    html = HOMEPAGE.read_text(encoding="utf-8")
    have = existing_hrefs(html)
    to_add = [p for p in new_posts if f"/blog/{p['slug']}" not in have]
    if not to_add:
        return False
    anchor = '<!-- Article Grid -->\n    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1.25rem">'
    cards = "\n" + "".join(homepage_card(p) for p in sorted(to_add, key=lambda p: p["date"], reverse=True))
    html = insert_after(html, anchor, cards.strip("\n") + "\n")
    HOMEPAGE.write_text(html, encoding="utf-8")
    return True


def update_blog_index(new_posts: list[dict]) -> bool:
    html = BLOG_INDEX.read_text(encoding="utf-8")
    have = existing_hrefs(html)
    to_add = [p for p in new_posts if f"/blog/{p['slug']}" not in have]
    if not to_add:
        return False
    anchor = '<div class="articles-grid">'
    cards = "\n" + "".join(blog_index_card(p) for p in sorted(to_add, key=lambda p: p["date"], reverse=True))
    html = insert_after(html, anchor, cards.strip("\n") + "\n")

    # bump the "All Articles (N)" count if that label exists
    total = len(re.findall(r'class="article-card"', html))
    html = re.sub(
        r"All Articles \(\d+\)",
        f"All Articles ({total})",
        html,
    )
    BLOG_INDEX.write_text(html, encoding="utf-8")
    return True


def main() -> None:
    if not BLOG_DIR.exists():
        print("No blog/ directory found.", file=sys.stderr)
        sys.exit(1)

    args = [a for a in sys.argv[1:] if a.strip()]
    if args:
        # Explicit mode (used by the GitHub Action): only process the
        # specific files that were added in this push.
        post_files = []
        for a in args:
            fp = BLOG_DIR / Path(a).name
            if fp.exists() and fp.name != "index.html":
                post_files.append(fp)
            else:
                print(f"⚠️  Skipping {a} (not found in blog/)", file=sys.stderr)
    else:
        # Manual/local mode: scan everything. Useful the first time you
        # set this up, to backfill any posts missing a card. Safe to run
        # any time — it only ever adds cards, never removes or edits.
        post_files = sorted(
            f for f in BLOG_DIR.glob("*.html")
            if f.name != "index.html"
        )

    if not post_files:
        print("ℹ️  No blog post files to process.")
        return

    posts = [build_post_meta(f) for f in post_files]

    changed_home = update_homepage(posts)
    changed_blog = update_blog_index(posts)

    if changed_home or changed_blog:
        print("✅ Blog index updated with new post card(s).")
    else:
        print("ℹ️  No new posts found — nothing to update.")


if __name__ == "__main__":
    main()
