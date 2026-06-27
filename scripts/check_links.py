#!/usr/bin/env python3
"""
SalaryBit internal link checker.

Scans every .html file in the repo for <a href="...">, <link href="...">,
<script src="...">, and <img src="..."> references, resolves internal
(same-site) links and local file paths, and checks them for breakage.

Internal links are checked two ways:
  1. Local file existence check (does the target .html file exist in the repo?)
  2. Live HTTP check against the deployed site (catches case-sensitivity,
     GitHub Pages routing issues, redirects that fail, etc.)

External links (other domains) are skipped by default — this script is
scoped to "did I break my own site," not general link rot across the web.
Pass --check-external to also validate external links (slower, and some
sites block bots, so failures there are reported separately and treated
as warnings rather than hard failures).

Exit code is 0 if no broken internal links are found, 1 otherwise.
Always writes a machine-readable report to link_check_report.json so the
GitHub Action can build an Issue body from it.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

SITE_BASE = "https://salarybit.in"
DEFAULT_ROOT = Path(__file__).resolve().parent.parent

# Matches href="..."/src="..." (single or double quotes) inside any tag
LINK_RE = re.compile(r'''(?:href|src)\s*=\s*["']([^"'#][^"']*)["']''', re.IGNORECASE)

# File extensions we don't try to "check" as pages (binary/asset types where
# a HEAD request is enough and existence is the only thing that matters)
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:")

USER_AGENT = "SalaryBit-LinkChecker/1.0 (+https://github.com/trendz113/salarybit)"
TIMEOUT = 10
MAX_WORKERS = 8
RETRIES = 1


def find_html_files(root: Path):
    for p in root.rglob("*.html"):
        # skip anything under node_modules, .git, vendor dirs if present
        parts = set(p.parts)
        if any(skip in parts for skip in (".git", "node_modules", "vendor")):
            continue
        yield p


def extract_links(html_path: Path):
    text = html_path.read_text(encoding="utf-8", errors="ignore")
    links = []
    for m in LINK_RE.finditer(text):
        raw = m.group(1).strip()
        if not raw or raw.startswith(SKIP_SCHEMES):
            continue
        links.append(raw)
    return links


def classify_link(raw_link, source_file: Path, root: Path):
    """
    Returns a dict describing the link: its type (internal/external/anchor-only),
    and the resolved path/url to check.
    """
    parsed = urlparse(raw_link)

    # Absolute URL pointing at another domain
    if parsed.scheme in ("http", "https") and parsed.netloc:
        is_own_site = parsed.netloc.lower().lstrip("www.") == "salarybit.in"
        if is_own_site:
            path = parsed.path or "/"
            return {"type": "internal", "path": path, "url": raw_link}
        return {"type": "external", "path": None, "url": raw_link}

    # Protocol-relative //example.com/...
    if raw_link.startswith("//"):
        return {"type": "external", "path": None, "url": "https:" + raw_link}

    # Root-relative /path or relative path — internal to this site
    if parsed.path:
        if raw_link.startswith("/"):
            resolved_path = parsed.path
        else:
            # relative to the source file's directory, within the repo
            rel_dir = source_file.parent.relative_to(root)
            resolved_path = "/" + str((rel_dir / parsed.path)).replace("\\", "/")
            resolved_path = os.path.normpath(resolved_path).replace("\\", "/")
        return {"type": "internal", "path": resolved_path, "url": urljoin(SITE_BASE, resolved_path)}

    return {"type": "skip", "path": None, "url": None}


def local_file_exists(url_path: str, root: Path) -> bool:
    """
    Check whether a root-relative path corresponds to a real file in the repo,
    accounting for GitHub Pages conventions (directory -> index.html, no
    trailing slash -> try .html, etc.)
    """
    clean = url_path.split("?")[0].split("#")[0]
    candidates = []
    rel = clean.lstrip("/")

    if rel == "" or clean.endswith("/"):
        candidates.append(root / rel / "index.html")
    else:
        candidates.append(root / rel)
        if not rel.endswith(".html"):
            candidates.append(root / (rel + ".html"))
            candidates.append(root / rel / "index.html")

    return any(c.exists() for c in candidates)


def http_check(url: str):
    """
    Issue a HEAD request first (cheap), fall back to GET if HEAD isn't
    allowed (some static hosts / CDNs reject HEAD with 405).
    Returns (ok: bool, status: int|None, error: str|None)
    """
    req_headers = {"User-Agent": USER_AGENT}
    last_error = None

    for attempt in range(RETRIES + 1):
        for method in ("HEAD", "GET"):
            try:
                req = urllib.request.Request(url, headers=req_headers, method=method)
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    status = resp.status
                    if status < 400:
                        return True, status, None
                    # 4xx/5xx — try GET if we were doing HEAD, else give up this attempt
                    last_error = f"HTTP {status}"
                    continue
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}"
                if e.code not in (405, 403) or method == "GET":
                    # 405/403 on HEAD is worth retrying with GET; other codes are final
                    if e.code not in (405,):
                        break
                continue
            except urllib.error.URLError as e:
                last_error = str(e.reason)
                continue
            except Exception as e:  # noqa: BLE001 - report any unexpected failure
                last_error = str(e)
                continue
        if attempt < RETRIES:
            time.sleep(1.5)

    return False, None, last_error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-external", action="store_true",
                         help="Also HTTP-check external (off-site) links")
    parser.add_argument("--report", default="link_check_report.json",
                         help="Path to write the JSON report")
    parser.add_argument("--root", default=str(DEFAULT_ROOT),
                         help="Repo root to scan (defaults to the repo containing this script)")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    html_files = sorted(find_html_files(root))
    if not html_files:
        print("No .html files found — nothing to check.", file=sys.stderr)
        sys.exit(0)

    # Collect every (source_file, raw_link) pair, de-duplicated by resolved target
    internal_targets = {}   # resolved_path -> {"url":..., "sources": set()}
    external_targets = {}   # url -> {"sources": set()}

    for f in html_files:
        for raw in extract_links(f):
            info = classify_link(raw, f, root)
            rel_source = str(f.relative_to(root))
            if info["type"] == "internal":
                bucket = internal_targets.setdefault(info["path"], {"url": info["url"], "sources": set()})
                bucket["sources"].add(rel_source)
            elif info["type"] == "external" and args.check_external:
                bucket = external_targets.setdefault(info["url"], {"sources": set()})
                bucket["sources"].add(rel_source)

    broken_internal = []
    ok_internal_count = 0

    print(f"Scanning {len(html_files)} HTML file(s), {len(internal_targets)} unique internal link(s)...")

    for path, data in sorted(internal_targets.items()):
        # Step 1: does it exist as a file in the repo?
        exists_locally = local_file_exists(path, root)
        if exists_locally:
            ok_internal_count += 1
            continue

        # Step 2: not found locally — could still be a server route (e.g. /blog/
        # handled by Jekyll/11ty at build time) so confirm against the live site
        # before flagging it as broken.
        ok, status, error = http_check(data["url"])
        if ok:
            ok_internal_count += 1
            continue

        broken_internal.append({
            "path": path,
            "url": data["url"],
            "status": status,
            "error": error,
            "found_in": sorted(data["sources"]),
        })

    broken_external = []
    if args.check_external and external_targets:
        print(f"Checking {len(external_targets)} external link(s)...")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            future_to_url = {pool.submit(http_check, url): url for url in external_targets}
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                ok, status, error = future.result()
                if not ok:
                    broken_external.append({
                        "url": url,
                        "status": status,
                        "error": error,
                        "found_in": sorted(external_targets[url]["sources"]),
                    })

    report = {
        "site": SITE_BASE,
        "files_scanned": len(html_files),
        "internal_links_checked": len(internal_targets),
        "internal_links_ok": ok_internal_count,
        "internal_links_broken": broken_internal,
        "external_links_checked": len(external_targets) if args.check_external else 0,
        "external_links_broken": broken_external,
    }

    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nDone. {ok_internal_count}/{len(internal_targets)} internal links OK.")
    if broken_internal:
        print(f"\n❌ {len(broken_internal)} broken internal link(s):")
        for b in broken_internal:
            print(f"  {b['path']}  (in: {', '.join(b['found_in'])})  -> {b['error'] or b['status']}")
    if broken_external:
        print(f"\n⚠️  {len(broken_external)} broken external link(s) (warning only):")
        for b in broken_external:
            print(f"  {b['url']}  (in: {', '.join(b['found_in'])})  -> {b['error'] or b['status']}")

    # Only internal breakage fails the run; external sites breaking isn't "our" bug
    sys.exit(1 if broken_internal else 0)


if __name__ == "__main__":
    main()
