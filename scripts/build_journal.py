#!/usr/bin/env python3
"""Build the journal from content/journal/<slug>/<lang>.md (stdlib only).

  python3 scripts/build_journal.py            # write journal/…, ko/journal/… and replace the journal <url> entries in sitemap.xml
  python3 scripts/build_journal.py --check    # exit 1 if a generated file or the journal part of sitemap.xml is stale

Generated (en = /journal/, ko = /ko/journal/):
  journal/index.html, journal/<slug>/index.html
  ko/journal/index.html, ko/journal/<slug>/index.html
Only the languages in journal_md.LANGS (en, ko) get journal pages; the rest of the site is untouched.
Origin comes from CNAME. Journal pages load assets/journal.css; everything else reuses assets/site.css.
"""
import argparse
import html
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import journal_md  # noqa: E402

SITE_CSS = "/assets/site.css?v=20261124"
JOURNAL_CSS = "/assets/journal.css?v=20261120"
ICON = "/assets/icon.svg?v=20261119"
E = html.escape

STR = {
    "en": {
        "name": "Journal", "home": "/en/", "other": "ko", "other_label": "한국어",
        "lead": "Notes from making 오늘 어때: design choices, what we built, and what we changed.",
        "empty": "No posts yet.", "back": "← Journal", "theme": "Theme",
        "privacy": "Privacy Policy", "terms": "Terms of Use", "support": "Support",
        "desc_index": "Notes from making 오늘 어때, a date-scene game for iOS and Android.",
        "tagline": "오늘 어때 · ipe Studio",
    },
    "ko": {
        "name": "저널", "home": "/ko/", "other": "en", "other_label": "English",
        "lead": "「오늘 어때」를 만들며 남기는 기록 — 설계 선택, 만든 것, 바꾼 것.",
        "empty": "아직 글이 없어요.", "back": "← 저널", "theme": "테마",
        "privacy": "개인정보 처리방침", "terms": "이용약관", "support": "지원",
        "desc_index": "데이트 장면을 고르는 게임 「오늘 어때」를 만들며 남긴 기록.",
        "tagline": "오늘 어때 · ipe Studio",
    },
}

THEME_HEAD = ("<script>\ntry { var s = localStorage.getItem('todaydate-theme'); "
              "if (s === 'light' || s === 'dark') document.documentElement.dataset.theme = s; } catch (e) {}\n</script>")
THEME_JS = ("<script>\n(function () {\n  var b = document.querySelector('[data-theme-toggle]');\n  if (!b) return;\n"
            "  b.addEventListener('click', function () {\n    var r = document.documentElement;\n"
            "    var dark = r.dataset.theme ? r.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;\n"
            "    var next = dark ? 'light' : 'dark';\n    r.dataset.theme = next;\n"
            "    try { localStorage.setItem('todaydate-theme', next); } catch (e) {}\n  });\n})();\n</script>")


def origin(root):
    try:
        host = (Path(root) / "CNAME").read_text(encoding="utf-8").strip()
    except OSError:
        host = ""
    return "https://%s" % host if host else ""


def list_path(lang):
    """Root-relative URL of the list page, with trailing slash."""
    return "/journal/" if lang == "en" else "/ko/journal/"


def post_path(lang, slug):
    return list_path(lang) + slug + "/"


def file_of(url_path):
    """'/journal/x/' -> 'journal/x/index.html'."""
    return url_path.lstrip("/") + "index.html"


def head(lang, title, desc, url, alts, og_type):
    links = "\n".join('<link rel="alternate" hreflang="%s" href="%s">' % (k, E(v)) for k, v in alts)
    return f"""<!doctype html>
<html lang="{lang}" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<meta name="theme-color" content="#f7f5ed" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#131e19" media="(prefers-color-scheme: dark)">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{E(url)}">
<link rel="canonical" href="{E(url)}">
{links}
<link rel="icon" href="{ICON}" type="image/svg+xml">
<link rel="stylesheet" href="{SITE_CSS}">
<link rel="stylesheet" href="{JOURNAL_CSS}">
{THEME_HEAD}
</head>
"""


def chrome(lang, other_href):
    s = STR[lang]
    o = s["other"]
    return f"""<body>
<header>
  <div class="wrap bar">
    <a class="wordmark" href="{s['home']}">오늘 어때</a>
    <div class="bar-end">
      <a class="button secondary" href="{list_path(lang)}" aria-current="page">{s['name']}</a>
      <a class="button secondary" href="{E(other_href)}" hreflang="{o}" lang="{o}">{s['other_label']}</a>
      <button type="button" class="button secondary theme-toggle" data-theme-toggle aria-label="Switch dark/light">{s['theme']}</button>
    </div>
  </div>
</header>
"""


def footer(lang):
    s = STR[lang]
    h = s["home"]
    return f"""<footer>
  <div class="wrap">
    <p class="muted">{s['tagline']}</p>
    <nav aria-label="Support"><ul class="lang-list"><li><a href="{list_path(lang)}">{s['name']}</a></li><li><a href="{h}privacy/">{s['privacy']}</a></li><li><a href="{h}terms/">{s['terms']}</a></li><li><a href="{h}support/">{s['support']}</a></li></ul></nav>
  </div>
</footer>
{THEME_JS}
</body>
</html>
"""


def render_list(lang, site, posts):
    """posts: [(slug, meta)] newest first, only those that have a page in this language."""
    s = STR[lang]
    if posts:
        items = "".join(
            '<li class="jitem"><p class="muted"><time datetime="%s">%s</time></p>'
            '<h2><a href="%s">%s</a></h2><p class="muted">%s</p></li>'
            % (E(m["date"]), E(m["date"]), E(post_path(lang, slug)), E(m["title"]), E(m.get("description", "")))
            for slug, m in posts)
    else:
        items = '<li class="muted">%s</li>' % E(s["empty"])
    alts = [("en", site + list_path("en")), ("ko", site + list_path("ko")), ("x-default", site + list_path("en"))]
    url = site + list_path(lang)
    out = head(lang, "%s · 오늘 어때" % s["name"], s["desc_index"], url, alts, "website")
    out += chrome(lang, list_path(s["other"]))
    out += f"""<main id="main" class="wrap journal">
  <h1>{E(s['name'])}</h1>
  <p class="muted lead">{E(s['lead'])}</p>
  <ul class="jlist">{items}</ul>
</main>
"""
    return out + footer(lang)


def render_post(lang, slug, meta, body, has_other, site):
    s = STR[lang]
    alts = [("en", site + post_path("en", slug))]
    if has_other:
        alts.append(("ko", site + post_path("ko", slug)))
    alts.append(("x-default", site + post_path("en", slug)))
    other = post_path(s["other"], slug) if has_other else list_path(s["other"])
    desc = meta.get("description", "")
    out = head(lang, "%s · 오늘 어때" % meta["title"], desc, site + post_path(lang, slug), alts, "article")
    out += chrome(lang, other)
    out += f"""<main id="main" class="wrap journal-post">
  <p class="eyebrow"><a href="{list_path(lang)}">{E(s['name'])}</a> · <time datetime="{E(meta['date'])}">{E(meta['date'])}</time></p>
  <h1>{E(meta['title'])}</h1>
  <p class="muted lead">{E(desc)}</p>
  <div class="prose">
{journal_md.render(body)}
  </div>
  <p><a class="back" href="{list_path(lang)}">{E(s['back'])}</a></p>
</main>
"""
    return out + footer(lang)


def sort_key(item):
    slug, meta = item
    return (meta["date"], meta.get("time", ""), slug)


def build(root):
    """Return (files {repo-relative path: html}, entries [(loc, lastmod, lang, slug)]).
    Each list page is one entry (slug None); lastmod is the newest post's date."""
    root = Path(root)
    site = origin(root)
    posts = journal_md.load_posts(str(root))
    files, entries = {}, []
    by_lang = {lang: [] for lang in journal_md.LANGS}
    for slug in sorted(posts):
        langs = posts[slug]
        for lang in journal_md.LANGS:
            if lang not in langs:
                continue
            meta, body = langs[lang]
            for k in ("title", "date", "description"):
                if not meta.get(k):
                    raise ValueError("content/journal/%s/%s.md: front matter '%s' missing" % (slug, lang, k))
            has_other = all(x in langs for x in journal_md.LANGS)
            files[file_of(post_path(lang, slug))] = render_post(lang, slug, meta, body, has_other, site)
            by_lang[lang].append((slug, meta))
            entries.append((site + post_path(lang, slug), meta["date"], lang, slug))
    for lang in journal_md.LANGS:
        ordered = sorted(by_lang[lang], key=sort_key, reverse=True)
        files[file_of(list_path(lang))] = render_list(lang, site, ordered)
        lastmod = ordered[0][1]["date"] if ordered else None
        entries.append((site + list_path(lang), lastmod, lang, None))
    return files, entries


def sitemap_block(loc, lastmod, slug, entries, site):
    if slug is None:
        alts = [(c, site + list_path(c)) for c in journal_md.LANGS]
        alts.append(("x-default", site + list_path("en")))
    else:
        alts = [(c, site + post_path(c, slug)) for c in journal_md.LANGS
                if any(e[2] == c and e[3] == slug for e in entries)]
        alts.append(("x-default", site + post_path("en", slug)))
    lines = ["  <url>", "    <loc>%s</loc>" % E(loc)]
    if lastmod:
        lines.append("    <lastmod>%s</lastmod>" % lastmod)
    for code, href in alts:
        lines.append('    <xhtml:link rel="alternate" hreflang="%s" href="%s"/>' % (code, E(href)))
    lines.append("  </url>")
    return "\n".join(lines) + "\n"


def sitemap_text(root, entries, site):
    """Drop every journal <url> block from sitemap.xml and append the freshly built ones; other blocks stay as they are."""
    text = (Path(root) / "sitemap.xml").read_text(encoding="utf-8")
    blocks = re.findall(r"  <url>\n.*?  </url>\n", text, re.S)
    keep = [b for b in blocks if "/journal/" not in b]
    head_end = text.index("  <url>")
    tail = text[text.rindex("</urlset>"):]
    new = [sitemap_block(loc, lastmod, slug, entries, site)
           for loc, lastmod, _lang, slug in entries if lastmod]
    return text[:head_end] + "".join(keep) + "".join(new) + tail


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(HERE.parent))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    site = origin(root)
    if not site:
        print("CNAME missing: site origin unknown")
        return 1
    files, entries = build(root)
    sm = sitemap_text(root, entries, site)
    if a.check:
        stale = [rel for rel, text in files.items()
                 if not (root / rel).is_file() or (root / rel).read_text(encoding="utf-8") != text]
        if (root / "sitemap.xml").read_text(encoding="utf-8") != sm:
            stale.append("sitemap.xml")
        if stale:
            print("journal is stale — run: python3 scripts/build_journal.py\n  " + "\n  ".join(stale))
            return 1
        print("journal: up to date (%d pages)" % len(files))
        return 0
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    for base in ("journal", "ko/journal"):  # article pages whose source was deleted
        d = root / base
        if d.is_dir():
            for idx in d.glob("*/index.html"):
                if idx.relative_to(root).as_posix() not in files:
                    idx.unlink()
                    idx.parent.rmdir()
    (root / "sitemap.xml").write_text(sm, encoding="utf-8")
    print("journal: wrote %d pages" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
