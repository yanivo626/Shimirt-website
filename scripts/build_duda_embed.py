"""Builds prototype/duda-embed.html – the homepage sections only, ready to paste into a
Duda (webwecan) "Custom HTML" widget.

The full page (prototype/index.html) stays the source of truth for the future site.
This script derives the embed from it, so after every change to the full page run:

    python3 scripts/build_duda_embed.py

What changes for Duda:
- no <html>/<head>, no intro screen, header, footer or floating WhatsApp (Duda has its own)
- every CSS rule is scoped under #so-home so it cannot clash with the Duda theme
- only the FAQ structured data is kept (Duda's own SEO settings cover the rest)
- the contact form becomes buttons to the existing contact page / WhatsApp,
  because a form inside the widget has nowhere to send to
- the hero photo is embedded, so the paste works without uploading anything
"""
import base64
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "prototype/index.html"
OUT = ROOT / "prototype/duda-embed.html"
SCOPE = "#so-home"
BASE = "https://www.shimrit-design.co.il/"


def between(s, start, end):
    i = s.index(start)
    j = s.index(end, i)
    return s[i + len(start):j]


def scope_selector(sel):
    sel = sel.strip()
    if sel in (":root", "html", "body"):
        return SCOPE
    return f"{SCOPE} {sel}"


def scope_rules(css):
    """Prefix every selector with #so-home; leave @keyframes alone, recurse into @media."""
    out, i = [], 0
    while i < len(css):
        brace = css.find("{", i)
        if brace == -1:
            out.append(css[i:])
            break
        head = css[i:brace]
        # find the matching closing brace
        depth, j = 1, brace + 1
        while depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        body = css[brace + 1:j - 1]
        lead = head[: len(head) - len(head.lstrip())]
        prelude = head.strip()
        # comments before the rule stay as they are
        comments = ""
        while prelude.startswith("/*"):
            end = prelude.index("*/") + 2
            comments += prelude[:end] + "\n"
            prelude = prelude[end:].strip()
        if prelude.startswith("@keyframes"):
            out.append(f"{lead}{comments}{prelude} {{{body}}}")
        elif prelude.startswith("@media"):
            out.append(f"{lead}{comments}{prelude} {{{scope_rules(body)}}}")
        else:
            sels = [scope_selector(s) for s in prelude.split(",")]
            out.append(f"{lead}{comments}{', '.join(dict.fromkeys(sels))} {{{body}}}")
        i = j
    return "".join(out)


def main():
    page = SRC.read_text(encoding="utf-8")

    css = between(page, "<style>", "</style>")
    css = re.sub(r"html \{ scroll-behavior: smooth; \}\n", "", css)
    css = scope_rules(css)
    # the hero sits under Duda's own header, so it needs less top room
    css = css.replace(".hero-inner { position: relative; z-index: 1; padding: 120px var(--gutter) 90px; }",
                      ".hero-inner { position: relative; z-index: 1; padding: 90px var(--gutter) 90px; }")
    css += f"""
/* guard against the Duda theme */
{SCOPE} {{ direction: rtl; text-align: right; overflow: hidden; }}
{SCOPE} p, {SCOPE} ul, {SCOPE} ol, {SCOPE} blockquote {{ margin-top: 0; }}
{SCOPE} a {{ text-decoration-skip-ink: auto; }}
{SCOPE} .narrow, {SCOPE} .hero {{ text-align: center; }}
{SCOPE} .close-ctas {{ display: flex; flex-wrap: wrap; gap: 14px; align-self: center; }}
"""

    main_html = between(page, '<main id="top">', "</main>")
    # contact form -> buttons
    form = main_html[main_html.index('<form id="lead"'):main_html.index("</form>") + len("</form>")]
    main_html = main_html.replace(form, f"""<div class="close-ctas">
        <a class="btn gold" href="{BASE}צרו-קשר">לתיאום פגישת היכרות</a>
        <a class="btn ghost-light" href="{BASE}צרו-קשר">[כפתור וואטסאפ – יחובר למספר הסטודיו]</a>
      </div>""")

    # embed the hero photo
    img = ROOT / "prototype/assets/kitchen-suzy-levinson.jpg"
    data = "data:image/jpeg;base64," + base64.b64encode(img.read_bytes()).decode()
    main_html = main_html.replace('src="assets/kitchen-suzy-levinson.jpg"', f'src="{data}"')

    # keep only the FAQ structured data
    ld = json.loads(between(page, '<script type="application/ld+json">', "</script>"))
    faq = next(n for n in ld["@graph"] if n["@type"] == "FAQPage")
    faq = {"@context": "https://schema.org", **faq}

    # only the testimonial rotation script is needed
    script = between(page, "<script>\n", "</script>")
    testimonials = script[script.index("// testimonials"):script.index("document.getElementById(\"lead\")")]
    testimonials = testimonials.replace('document.querySelectorAll(".quote")', 'root.querySelectorAll(".quote")') \
                               .replace('document.querySelectorAll(".dots button")', 'root.querySelectorAll(".dots button")')

    out = f"""<!-- שמרית אוחיון – דף הבית, גרסה להדבקה ב-Duda (רכיב Custom HTML).
     נוצר אוטומטית מ-prototype/index.html על ידי scripts/build_duda_embed.py – לא לערוך ידנית. -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bellefair&family=Assistant:wght@300;400;600&display=swap" rel="stylesheet">
<style>
{css}
</style>
<div id="so-home" dir="rtl" lang="he">
{main_html}
</div>
<script type="application/ld+json">
{json.dumps(faq, ensure_ascii=False, indent=2)}
</script>
<script>
(function () {{
  var root = document.getElementById("so-home");
  if (!root) return;
  {testimonials.strip()}
}})();
</script>
"""
    OUT.write_text(out, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(out) // 1024} KB)")


if __name__ == "__main__":
    main()
