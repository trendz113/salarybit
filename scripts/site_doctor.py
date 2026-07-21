#!/usr/bin/env python3
"""
site_doctor.py — one script, drop it in scripts/ and it auto-fixes
what's safely fixable across every .html page, and reports what needs
a human decision.

AUTO-FIXED (deterministic, safe to apply without judgment calls):
  - Missing og:title / og:description / og:url / og:image / twitter:* tags
  - Missing <link rel="canonical"> tag
  - Pages missing from sitemap.xml

REPORTED ONLY (needs a human — this script will NOT guess):
  - Pages with no <title> or no meta description at all
  - <img> tags with no alt attribute (accessibility/SEO)
  - http:// (non-https) links, which could be broken mixed content
  - Broken internal links (delegated to scripts/check_links.py if present)

Usage:
    python3 scripts/site_doctor.py            # fix in place, print report
    python3 scripts/site_doctor.py --check    # dry run; exit 1 if anything
                                                 needs attention (fixable or not)
"""
import html
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

DOMAIN = "https://salarybit.in"
DEFAULT_IMAGE = f"{DOMAIN}/og-image.png"
SITE_NAME = "SalaryBit"
IMG_W, IMG_H = "1200", "630"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "node_modules", "scripts", "certs", ".github"}
SITEMAP_PATH = os.path.join(ROOT, "sitemap.xml")

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
DESC_RE = re.compile(
    r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']\s*/?>',
    re.IGNORECASE | re.DOTALL,
)
OGTITLE_RE = re.compile(r'<meta\s+property=["\']og:title["\'][^>]*>', re.IGNORECASE)
OGIMAGE_RE = re.compile(r'property=["\']og:image["\']', re.IGNORECASE)
TWIMAGE_RE = re.compile(r'name=["\']twitter:image["\']', re.IGNORECASE)
TWCARD_RE = re.compile(r'name=["\']twitter:card["\']', re.IGNORECASE)
CANONICAL_RE = re.compile(r'<link\s+rel=["\']canonical["\']', re.IGNORECASE)
HEAD_CLOSE_RE = re.compile(r"</head>", re.IGNORECASE)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
IMG_ALT_RE = re.compile(r'\balt\s*=\s*["\']', re.IGNORECASE)
HTTP_LINK_RE = re.compile(r'(?:href|src)\s*=\s*["\']http://([^"\']+)["\']', re.IGNORECASE)


def find_html_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(".html"):
                yield os.path.join(dirpath, fn)


def page_url(path):
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    if rel == "index.html":
        return f"{DOMAIN}/"
    if rel.endswith("/index.html"):
        return f"{DOMAIN}/{rel[:-len('index.html')]}"
    return f"{DOMAIN}/{rel}"


def full_og_block(title, desc, url):
    title, desc = html.escape(title, quote=True), html.escape(desc, quote=True)
    return f"""<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:image" content="{DEFAULT_IMAGE}">
<meta property="og:image:width" content="{IMG_W}">
<meta property="og:image:height" content="{IMG_H}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{DEFAULT_IMAGE}">
"""


def fix_meta_tags(path, content, report):
    """Returns (new_content, changed_bool). Fixes OG/Twitter + canonical."""
    changed = False
    title_match = TITLE_RE.search(content)
    title = html.unescape(title_match.group(1).strip()) if title_match else SITE_NAME
    if not title_match:
        report["no_title"].append(os.path.relpath(path, ROOT))

    desc_match = DESC_RE.search(content)
    if not desc_match:
        report["no_description"].append(os.path.relpath(path, ROOT))

    url = page_url(path)
    ogtitle_match = OGTITLE_RE.search(content)

    if not ogtitle_match:
        desc = (
            html.unescape(desc_match.group(1).strip())
            if desc_match
            else f"Free tool from {SITE_NAME} for Indian salaried professionals. No login, no data stored."
        )
        block = full_og_block(title, desc, url)
        head_match = HEAD_CLOSE_RE.search(content)
        if head_match:
            content = content[: head_match.start()] + block + content[head_match.start() :]
            changed = True
    else:
        extra = []
        if not OGIMAGE_RE.search(content):
            extra += [
                f'<meta property="og:image" content="{DEFAULT_IMAGE}">',
                f'<meta property="og:image:width" content="{IMG_W}">',
                f'<meta property="og:image:height" content="{IMG_H}">',
            ]
        if not TWCARD_RE.search(content):
            extra.append('<meta name="twitter:card" content="summary_large_image">')
        if not TWIMAGE_RE.search(content):
            extra.append(f'<meta name="twitter:image" content="{DEFAULT_IMAGE}">')
        if extra:
            insert_pos = ogtitle_match.end()
            content = content[:insert_pos] + "\n" + "\n".join(extra) + content[insert_pos:]
            changed = True

    if not CANONICAL_RE.search(content):
        canon_tag = f'<link rel="canonical" href="{url}">\n'
        head_match = HEAD_CLOSE_RE.search(content)
        if head_match:
            content = content[: head_match.start()] + canon_tag + content[head_match.start() :]
            changed = True

    # Report-only checks (no auto-fix — needs human judgment)
    for img_tag in IMG_TAG_RE.findall(content):
        if not IMG_ALT_RE.search(img_tag):
            report["missing_alt_count"] += 1
            break  # count file once, not per image, to keep the report readable
    for http_url in HTTP_LINK_RE.findall(content):
        report["http_links"].append((os.path.relpath(path, ROOT), "http://" + http_url))

    return content, changed


def fix_sitemap(all_pages, report):
    """Ensures every page has a <url><loc> entry in sitemap.xml. Returns changed_bool."""
    if not os.path.exists(SITEMAP_PATH):
        report["no_sitemap"] = True
        return False

    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    tree = ET.parse(SITEMAP_PATH)
    root_el = tree.getroot()

    existing = {loc.text.strip() for loc in root_el.findall(f"{ns}url/{ns}loc") if loc.text}
    missing = [u for u in all_pages if u not in existing]

    if not missing:
        return False

    for url in missing:
        url_el = ET.SubElement(root_el, f"{ns}url")
        loc_el = ET.SubElement(url_el, f"{ns}loc")
        loc_el.text = url
        report["sitemap_added"].append(url)

    ET.indent(tree, space="  ")
    tree.write(SITEMAP_PATH, encoding="UTF-8", xml_declaration=True)
    return True


def run_link_checker():
    """Delegates to the repo's own scripts/check_links.py if present (report-only)."""
    checker = os.path.join(ROOT, "scripts", "check_links.py")
    if not os.path.exists(checker):
        return None
    try:
        result = subprocess.run(
            [sys.executable, checker], capture_output=True, text=True, timeout=180
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:  # network issues etc. — don't fail the whole run over this
        return None, "", str(e)


def main():
    check_only = "--check" in sys.argv
    report = {
        "no_title": [],
        "no_description": [],
        "missing_alt_count": 0,
        "http_links": [],
        "sitemap_added": [],
        "no_sitemap": False,
    }

    changed_files = []
    all_page_urls = []

    for path in find_html_files():
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        new_content, changed = fix_meta_tags(path, content, report)
        all_page_urls.append(page_url(path))
        if changed:
            changed_files.append(os.path.relpath(path, ROOT))
            if not check_only:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)

    sitemap_changed = fix_sitemap(all_page_urls, report) if not check_only else False
    if check_only and os.path.exists(SITEMAP_PATH):
        # dry-run peek at sitemap gaps without writing
        ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        tree = ET.parse(SITEMAP_PATH)
        existing = {loc.text.strip() for loc in tree.getroot().findall(f"{ns}url/{ns}loc") if loc.text}
        report["sitemap_added"] = [u for u in all_page_urls if u not in existing]

    print("=" * 60)
    print("SITE DOCTOR REPORT")
    print("=" * 60)

    verb = "Would fix" if check_only else "Fixed"
    if changed_files:
        print(f"\n[AUTO-FIXED] OG/Twitter/canonical tags — {verb} {len(changed_files)} page(s):")
        for f in changed_files:
            print(f"  - {f}")
    else:
        print("\n[AUTO-FIXED] OG/Twitter/canonical tags — nothing to do, all pages OK.")

    if report["sitemap_added"]:
        print(f"\n[AUTO-FIXED] sitemap.xml — {verb} {len(report['sitemap_added'])} missing URL(s):")
        for u in report["sitemap_added"]:
            print(f"  - {u}")
    elif report["no_sitemap"]:
        print("\n[NEEDS ATTENTION] sitemap.xml not found — create one manually.")
    else:
        print("\n[AUTO-FIXED] sitemap.xml — already complete.")

    print("\n[NEEDS REVIEW] The following can't be safely auto-fixed:")
    any_manual = False
    if report["no_title"]:
        any_manual = True
        print(f"  - {len(report['no_title'])} page(s) with no <title> tag: {report['no_title']}")
    if report["no_description"]:
        any_manual = True
        print(f"  - {len(report['no_description'])} page(s) with no meta description: {report['no_description']}")
    if report["missing_alt_count"]:
        any_manual = True
        print(f"  - {report['missing_alt_count']} page(s) have <img> tags missing alt text")
    if report["http_links"]:
        any_manual = True
        print(f"  - {len(report['http_links'])} non-HTTPS (http://) link(s) found:")
        for f, u in report["http_links"]:
            print(f"      {f}: {u}")

    link_result = run_link_checker()
    if link_result is not None:
        rc, out, err = link_result
        if rc == 1:
            any_manual = True
            print("\n[NEEDS REVIEW] scripts/check_links.py found broken internal links:")
            print(out[-3000:])  # tail, keep CI logs readable
        elif rc == 0:
            print("\n[OK] scripts/check_links.py — no broken internal links.")
        else:
            print(f"\n[WARN] scripts/check_links.py could not run cleanly: {err[:500]}")

    if not any_manual:
        print("  (none — nice)")

    print("\n" + "=" * 60)

    made_or_needed_changes = bool(changed_files) or bool(report["sitemap_added"]) or any_manual
    if check_only and made_or_needed_changes:
        sys.exit(1)


if __name__ == "__main__":
    main()
