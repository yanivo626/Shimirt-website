"""Builds data/url-inventory.csv from data/old-sitemap.xml with a migration plan per URL."""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.shimrit-design.co.il"

# slug -> (type, action, note). Anything not listed and with priority 0.8 is an article kept as-is.
CLASSIFY = {
    "": ("home", "keep", "דף הבית"),
    "השירותים-שלנו": ("service-hub", "keep", "עמוד ריכוז שירותים"),
    "עיצוב-משרדים-וחללי-מסחר": ("service", "keep", "חפיפה עם עיצוב-חללים-מסחריים / עיצוב-חללי-מסחר"),
    "עיצוב-חללים-מסחריים": ("service", "keep", "חפיפה עם עיצוב-משרדים-וחללי-מסחר"),
    "פגישת-יעוץ-בזום": ("service", "keep", ""),
    "יעוץ-מקיף-דירת-קבלן": ("service", "keep", ""),
    "יעוץ-מקיף-style": ("service", "keep", ""),
    "יעוץ-ממוקד": ("service", "keep", ""),
    "יעוץ-עיצוב-לבית-פרטי": ("service", "keep", ""),
    "חבילת-ייעוץ-לעיצוב-הבית-מותאם-מחשב": ("service", "keep", ""),
    "עיצוב-פנים-בית-פרטי": ("service", "keep", ""),
    "תכנון-ושדרוג-מטבחים": ("service", "keep", ""),
    "עיצוב-חדרי-רחצה": ("service", "keep", "חפיפה עם המאמר עיצוב-חדרי-רחצה-יוקרתיים"),
    "סטיילינג-לחדר-שינה": ("service", "keep", ""),
    "סטיילינג-והלבשה-לדירת-קבלן": ("service", "keep", ""),
    "הום-סטיילינג": ("service", "keep", "חפיפה עם המאמר הום-סטיילינג-לבית"),
    "שינויי-דיירים": ("service", "keep", "חפיפה עם שינויי-דיירים-דירת-קבלן-תל-אביב"),
    "עיצוב-סינרגי": ("service", "keep", "עמוד העוגן של 'עיצוב סינרגי' – אשכול עם 7 עמודים נוספים"),
    "עיצוב-סינרגי-תל-אביב": ("service-local", "keep", "אשכול סינרגי – כמעט זהה ל-עיצוב-פנים-סינרגי-בתל-אביב"),
    "עיצוב-פנים-סינרגי-בתל-אביב": ("service-local", "keep", "אשכול סינרגי – כמעט זהה ל-עיצוב-סינרגי-תל-אביב"),
    "מפת-עיצוב-סינרגי": ("service", "keep", "אשכול סינרגי"),
    "פנג-שואי-חדר-שינה": ("service", "keep", "חפיפה עם המאמר feng-shui-interior-design"),
    "שמרית-אוחיון": ("about", "keep", "4 עמודי 'שמרית אוחיון' – לבדוק ב-GSC איזה מדורג"),
    "שמרית-אוחיון-מעצבת-פנים": ("about-variant", "keep", "וריאנט שם המותג"),
    "שמרית-אוחיון-מעצבת-פנים-מומלצת": ("about-variant", "keep", "וריאנט שם המותג"),
    "שמרית-אוחיון-עיצוב-פנים": ("about-variant", "keep", "וריאנט שם המותג"),
    "לקוחות-ממליצים": ("testimonials", "keep", ""),
    "שאלות-ותשובות": ("faq", "keep", "FAQPage schema"),
    "מהתקשורת": ("press", "keep", ""),
    "צרו-קשר": ("contact", "keep", ""),
    "הצהרת-נגישות": ("legal", "keep", ""),
    "מאמרים": ("blog-index", "keep", "עמוד המאמרים הראשי"),
    "blog": ("blog-index", "301 -> /מאמרים", "כפילות של עמוד המאמרים"),
    "Thank-You": ("utility", "keep + noindex", "עמוד תודה אחרי טופס (מדידת המרות)"),
    "copy-of-בית": ("junk", "301 -> /", "עותק של דף הבית"),
    "קמפיין-מעצבת-פנים": ("landing", "keep + noindex", "דף נחיתה לקמפיין ממומן"),
    "דף-נחיתה-עיצוב-פנים-אתר": ("landing", "keep + noindex", "דף נחיתה לקמפיין ממומן"),
    "עיצוב-פנים-במודיעין": ("service-local", "keep", "עמוד מקומי – מודיעין"),
    "מעצבת-פנים-במרכז": ("service-local", "keep", "עמוד מקומי – מרכז"),
    "my-post1c08120d": ("article", "keep (slug בעייתי)", "slug אוטומטי – לשקול 301 לכתובת עם מילות מפתח רק אם אין לו תנועה"),
    "my-post8e8006e0": ("article", "keep (slug בעייתי)", "slug אוטומטי – לשקול 301 לכתובת עם מילות מפתח רק אם אין לו תנועה"),
    "my-post21ae5928": ("article", "keep (slug בעייתי)", "slug אוטומטי – לשקול 301 לכתובת עם מילות מפתח רק אם אין לו תנועה"),
    "eitzuv-sinergi-tmunot-lakir": ("article", "keep", "אשכול סינרגי"),
    "עיצוב-פנים-סינרגי": ("article", "keep", "אשכול סינרגי"),
    "איך-עיצוב-סינרגי-משפיע-על-האווירה-בבית": ("article", "keep", "אשכול סינרגי"),
    "עיצוב-סינרגי-המפתח-לשינוי-חווית-המגורים-שלכם": ("article", "keep", "אשכול סינרגי"),
}

PROJECT_SLUGS = {
    "עיצוב-מודרני-מוקפד-במודיעין", "השבחת-נכסים--עיצוב-דירה-למכירה--פתח-תקווה", "יהלום-תאורה",
    "משפחת-פלג", "עיצוב-דירת-קבלן-ברחובות-בסגנון-קלאסי-מודרני", "עיצוב-ותכנון-פנים-לבית-פרטי-במרכז",
    "בית-פרטי-בראשון-לציון", "עיצוב-דירה-אורבנית--מודיעין", "משרד-נוסטלגי-במודיעין",
    "שיפוץ-ועיצוב-טריפלקס-במבשרת-ציון", "דופלקס---פתח-תקווה", "דירה-מודרנית-חמה--מודיעין",
    "דירת-גג-מטריפה--שכונת-בבלי-תל-אביב", "עיצוב-פנטהואז-מודרני-קלאסי-במודיעין", "פנטהאוז-יוקרתי-במודיעין",
    "עיצוב-פנים-יוקרתי-לדירה-בראשון-לציון", "עיצוב-בר-קפה-במודיעין", "וריסה-ובניה-מחדש-בשיפוץ-במודיעין",
    "שיפוץ-בית-פרטי-מודרני-אקלקטי-במודיעין", "עיצוב-דירת-יוקרה-משפחת-בן-שבת", "מהפך-לדירת-קבלן-ביהוד",
    "דופלקס-ייחודי---דרזי",
}


def main():
    xml = (ROOT / "data/old-sitemap.xml").read_text(encoding="utf-8")
    rows = []
    for loc, prio, lastmod in re.findall(
        r"<loc>(.*?)</loc><priority>(.*?)</priority><lastmod>(.*?)</lastmod>", xml
    ):
        slug = loc[len(BASE):].lstrip("/")
        if slug in CLASSIFY:
            kind, action, note = CLASSIFY[slug]
        elif slug in PROJECT_SLUGS:
            kind, action, note = "project", "keep", ""
        elif prio == "0.8":
            kind, action, note = "article", "keep", ""
        else:
            kind, action, note = "unclassified", "review", ""
        rows.append({"old_url": loc, "path": "/" + slug, "type": kind, "priority": prio,
                     "lastmod": lastmod, "action": action, "notes": note})

    out = ROOT / "data/url-inventory.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    counts = {}
    for r in rows:
        counts[r["type"]] = counts.get(r["type"], 0) + 1
    print(len(rows), "urls")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
