"""Crawl the current Duda site (every URL in data/old-sitemap.xml plus pages linked from them)
and save everything the migration needs:

  data/old-site/html/<id>.html     raw HTML of each page
  data/old-site/pages.json         per page: status, redirects, title, meta, canonical, robots,
                                   headings, main text, images (+alt), links, forms, JSON-LD
  data/old-site/site.json          site-wide: menu, footer links, fonts, CSS colors, tracking IDs
  data/old-site/pages.csv          one row per page, for review in Excel
  data/old-site/images/            every content image (with --images)

Run from the repo root once the domain is reachable from this environment:

    python3 scripts/crawl_old_site.py            # pages only
    python3 scripts/crawl_old_site.py --images   # also download images
"""
import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/old-site"
HOST = "www.shimrit-design.co.il"
UA = "Mozilla/5.0 (site migration crawler)"
DELAY = 1.0  # seconds between requests – be gentle with the live site

TRACKING = {
    "ga4": r"G-[A-Z0-9]{6,}",
    "universal_analytics": r"UA-\d{4,}-\d+",
    "google_ads": r"AW-\d{6,}",
    "gtm": r"GTM-[A-Z0-9]{4,}",
    "facebook_pixel": r"fbq\(['\"]init['\"],\s*['\"](\d{10,})",
    "hotjar": r"hjid:\s*(\d+)",
    "clarity": r"clarity\.ms/tag/([a-z0-9]+)",
}


def sitemap_urls():
    xml = (ROOT / "data/old-sitemap.xml").read_text(encoding="utf-8")
    return re.findall(r"<loc>(.*?)</loc>", xml)


def is_internal(url):
    return urlparse(url).netloc in ("", HOST, HOST.replace("www.", ""))


def text_of(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def parse_page(url, resp):
    soup = BeautifulSoup(resp.text, "html.parser")
    head = soup.head or soup

    def meta(name=None, prop=None):
        tag = head.find("meta", attrs={"name": name} if name else {"property": prop})
        return tag.get("content", "").strip() if tag else ""

    canonical = head.find("link", rel="canonical")
    ld = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            ld.append(json.loads(s.string or ""))
        except ValueError:
            ld.append({"_unparsed": (s.string or "")[:500]})

    body = soup.body or soup
    for junk in body(["script", "style", "noscript", "svg"]):
        junk.extract()
    header = body.find("header")
    footer = body.find("footer")
    main = body.find("main") or body

    images = []
    for img in main.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if src and not src.startswith("data:"):
            images.append({"src": urljoin(url, src), "alt": img.get("alt", "")})
    for el in main.find_all(style=re.compile(r"background-image")):
        m = re.search(r"url\(['\"]?(.*?)['\"]?\)", el["style"])
        if m and not m.group(1).startswith("data:"):
            images.append({"src": urljoin(url, m.group(1)), "alt": "", "background": True})

    links = []
    for a in main.find_all("a", href=True):
        href = urljoin(url, a["href"])
        links.append({"href": href, "text": text_of(a), "internal": is_internal(href)})

    forms = []
    for f in body.find_all("form"):
        forms.append({
            "action": f.get("action", ""),
            "fields": [{"name": i.get("name", ""), "type": i.get("type", i.name), "label": i.get("placeholder", "") or i.get("aria-label", "")}
                       for i in f.find_all(["input", "select", "textarea"]) if i.get("type") != "hidden"],
        })

    return {
        "url": url,
        "path": unquote(urlparse(url).path) or "/",
        "status": resp.status_code,
        "final_url": resp.url,
        "redirected": [r.url for r in resp.history],
        "title": text_of(head.find("title")),
        "description": meta("description"),
        "robots": meta("robots"),
        "canonical": canonical.get("href", "") if canonical else "",
        "og_title": meta(prop="og:title"),
        "og_image": meta(prop="og:image"),
        "h1": [text_of(h) for h in main.find_all("h1")],
        "h2": [text_of(h) for h in main.find_all("h2")],
        "h3": [text_of(h) for h in main.find_all("h3")],
        "text": text_of(main),
        "words": len(text_of(main).split()),
        "images": images,
        "links": links,
        "forms": forms,
        "json_ld": ld,
        "_header_links": [{"href": urljoin(url, a["href"]), "text": text_of(a)} for a in (header.find_all("a", href=True) if header else [])],
        "_footer_links": [{"href": urljoin(url, a["href"]), "text": text_of(a)} for a in (footer.find_all("a", href=True) if footer else [])],
    }


def site_wide(raw_html, pages):
    fonts, colors, css_links, tracking = Counter(), Counter(), set(), {}
    for html in raw_html:
        for m in re.finditer(r"font-family:\s*([^;\"}]+)", html):
            fonts[m.group(1).strip().split(",")[0].strip("'\" ")] += 1
        for m in re.finditer(r"#[0-9a-fA-F]{6}\b|rgba?\([^)]+\)", html):
            colors[m.group(0).lower()] += 1
        for m in re.finditer(r'href="([^"]+\.css[^"]*|https://fonts\.googleapis\.com[^"]+)"', html):
            css_links.add(m.group(1))
        for key, pat in TRACKING.items():
            for m in re.finditer(pat, html):
                tracking.setdefault(key, set()).add(m.group(1) if m.groups() else m.group(0))
    home = next((p for p in pages if p["path"] in ("/", "")), pages[0] if pages else {})
    return {
        "menu": home.get("_header_links", []),
        "footer": home.get("_footer_links", []),
        "fonts": fonts.most_common(20),
        "colors": colors.most_common(30),
        "css_and_font_links": sorted(css_links),
        "tracking_ids": {k: sorted(v) for k, v in tracking.items()},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", action="store_true", help="also download content images")
    args = ap.parse_args()

    (OUT / "html").mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = UA

    queue, seen, pages, raw = list(sitemap_urls()), set(), [], []
    while queue:
        url = queue.pop(0).split("#")[0]
        if url in seen or not is_internal(url):
            continue
        seen.add(url)
        try:
            resp = s.get(url, timeout=30)
        except requests.RequestException as e:
            print(f"!! {url}: {e}", file=sys.stderr)
            pages.append({"url": url, "status": "error", "error": str(e)})
            continue
        pid = hashlib.sha1(url.encode()).hexdigest()[:10]
        (OUT / "html" / f"{pid}.html").write_text(resp.text, encoding="utf-8")
        page = parse_page(url, resp)
        page["id"] = pid
        pages.append(page)
        raw.append(resp.text)
        print(f"{resp.status_code} {page['path']}  words={page['words']}  imgs={len(page['images'])}")
        for link in page["links"]:  # pick up pages that are linked but missing from the sitemap
            href = link["href"].split("#")[0].split("?")[0]
            if link["internal"] and href not in seen and not re.search(r"\.(jpe?g|png|webp|gif|pdf|svg)$", href, re.I):
                queue.append(href)
        time.sleep(DELAY)

    site = site_wide(raw, [p for p in pages if p.get("status") == 200])
    for p in pages:
        p.pop("_header_links", None)
        p.pop("_footer_links", None)
    (OUT / "pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "site.json").write_text(json.dumps(site, ensure_ascii=False, indent=1), encoding="utf-8")

    with (OUT / "pages.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["path", "status", "in_sitemap", "title", "description", "h1_count", "h1", "words", "images", "images_without_alt", "forms"])
        in_map = set(sitemap_urls())
        for p in pages:
            if p.get("status") == "error":
                w.writerow([p["url"], "error", p["url"] in in_map])
                continue
            w.writerow([p["path"], p["status"], p["url"] in in_map, p["title"], p["description"], len(p["h1"]),
                        " | ".join(p["h1"]), p["words"], len(p["images"]), sum(1 for i in p["images"] if not i["alt"]), len(p["forms"])])

    if args.images:
        img_dir = OUT / "images"
        img_dir.mkdir(exist_ok=True)
        for src in sorted({i["src"] for p in pages for i in p.get("images", [])}):
            name = hashlib.sha1(src.encode()).hexdigest()[:12] + Path(urlparse(src).path).suffix[:5]
            if (img_dir / name).exists():
                continue
            try:
                (img_dir / name).write_bytes(s.get(src, timeout=60).content)
                time.sleep(DELAY / 2)
            except requests.RequestException as e:
                print(f"!! image {src}: {e}", file=sys.stderr)

    print(f"\n{len(pages)} pages, {sum(1 for p in pages if p.get('status') == 200)} OK -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
