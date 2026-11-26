#!/usr/bin/env python3
"""Build the journal from content/journal/<slug>/<lang>.md (stdlib only).

  python3 scripts/build_journal.py            # regenerate journal pages and sitemap
  python3 scripts/build_journal.py --check    # exit 1 if the generated output is stale

English keeps /journal/; other languages use /<language>/journal/.
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
JOURNAL_CSS = "/assets/journal.css?v=20261126"
ICON = "/assets/icon.svg?v=20261119"
E = html.escape
LEGACY_POSTS = {"idea-to-testflight-in-one-day", "no-ads-on-device", "rainy-season-pack",
                "scene-backgrounds", "thirty-scenes"}

STR = {
    "en": {
        "name": "Journal",
        "lead": "Notes from making 오늘 어때: design choices, what we built, and what we changed.",
        "empty": "No posts yet.", "back": "← Journal", "theme": "Theme",
        "privacy": "Privacy Policy", "terms": "Terms of Use", "support": "Support",
        "desc_index": "Notes from making 오늘 어때, a date-scene game for iOS and Android.",
        "tagline": "오늘 어때 · ipe Studio",
    },
    "ko": {
        "name": "저널",
        "lead": "「오늘 어때」를 만들며 남기는 기록 — 설계 선택, 만든 것, 바꾼 것.",
        "empty": "아직 글이 없어요.", "back": "← 저널", "theme": "테마",
        "privacy": "개인정보 처리방침", "terms": "이용약관", "support": "지원",
        "desc_index": "데이트 장면을 고르는 게임 「오늘 어때」를 만들며 남긴 기록.",
        "tagline": "오늘 어때 · ipe Studio",
    },
}

NAMES = dict(zip(journal_md.LANGS, (
    "English", "한국어", "日本語", "繁體中文", "Español", "Português (Brasil)",
    "Français", "Deutsch", "Bahasa Indonesia", "ไทย", "Tiếng Việt", "Türkçe",
)))
# Journal title, theme toggle, privacy, terms, support.
LABELS = {
    "ja": ("ジャーナル", "テーマ", "プライバシーポリシー", "利用規約", "サポート"),
    "zh-Hant": ("開發日誌", "主題", "隱私權政策", "使用條款", "支援"),
    "es": ("Diario", "Tema", "Política de privacidad", "Condiciones de uso", "Ayuda"),
    "pt-BR": ("Diário", "Tema", "Política de privacidade", "Termos de uso", "Suporte"),
    "fr": ("Journal", "Thème", "Politique de confidentialité", "Conditions d’utilisation", "Assistance"),
    "de": ("Journal", "Design", "Datenschutzerklärung", "Nutzungsbedingungen", "Hilfe"),
    "id": ("Jurnal", "Tema", "Kebijakan privasi", "Ketentuan penggunaan", "Bantuan"),
    "th": ("บันทึก", "ธีม", "นโยบายความเป็นส่วนตัว", "ข้อกำหนดการใช้งาน", "ความช่วยเหลือ"),
    "vi": ("Nhật ký", "Giao diện", "Chính sách quyền riêng tư", "Điều khoản sử dụng", "Hỗ trợ"),
    "tr": ("Günlük", "Tema", "Gizlilik Politikası", "Kullanım Koşulları", "Destek"),
}
for code, labels in LABELS.items():
    STR[code] = dict(zip(("name", "theme", "privacy", "terms", "support"), labels))
    STR[code].update(back="← " + labels[0], desc_index=labels[0] + " · 오늘 어때",
                     tagline="오늘 어때 · ipe Studio")


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
    return "/journal/" if lang == "en" else "/%s/journal/" % lang.lower()


def journal_paths():
    return tuple(list_path(lang).strip("/") for lang in journal_md.LANGS)


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


def alternates(paths, site):
    links = [(lang, site + path) for lang, path in paths.items()]
    if "en" in paths:
        links.append(("x-default", site + paths["en"]))
    return links


def chrome(lang):
    s = STR[lang]
    return f"""<body>
<header>
  <div class="wrap bar">
    <a class="wordmark" href="/{lang.lower()}/">오늘 어때</a>
    <div class="bar-end">
      <a class="button secondary" href="{list_path(lang)}">{E(s["name"])}</a>
      <button type="button" class="button secondary theme-toggle" data-theme-toggle>{E(s["theme"])}</button>
    </div>
  </div>
</header>
"""


def language_links(lang, paths):
    items = "".join(
        f'<li><a href="{E(path)}" hreflang="{code}" lang="{code}">{E(NAMES[code])}</a></li>'
        for code, path in paths.items() if code != lang
    )
    return f'<ul class="lang-list journal-languages">{items}</ul>' if items else ""


def footer(lang):
    s = STR[lang]
    h = f"/{lang.lower()}/"
    return f"""<footer>
  <div class="wrap">
    <p class="muted">{s['tagline']}</p>
    <nav aria-label="{E(s['support'])}"><ul class="lang-list"><li><a href="{list_path(lang)}">{s['name']}</a></li><li><a href="{h}privacy/">{s['privacy']}</a></li><li><a href="{h}terms/">{s['terms']}</a></li><li><a href="{h}support/">{s['support']}</a></li></ul></nav>
  </div>
</footer>
{THEME_JS}
</body>
</html>
"""


def render_list(lang, site, posts, paths):
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
    url = site + list_path(lang)
    out = head(lang, "%s · 오늘 어때" % s["name"], s["desc_index"], url, alternates(paths, site), "website")
    out += chrome(lang)
    lead = '<p class="muted lead">%s</p>' % E(s["lead"]) if "lead" in s else ""
    out += f"""<main id="main" class="wrap journal">
  <h1>{E(s['name'])}</h1>
  {lead}
  {language_links(lang, paths)}
  <ul class="jlist">{items}</ul>
</main>
"""
    return out + footer(lang)


def render_post(lang, slug, meta, body, paths, site):
    s = STR[lang]
    desc = meta.get("description", "")
    out = head(lang, "%s · 오늘 어때" % meta["title"], desc, site + post_path(lang, slug), alternates(paths, site), "article")
    out += chrome(lang)
    out += f"""<main id="main" class="wrap journal-post">
  <p class="eyebrow"><a href="{list_path(lang)}">{E(s['name'])}</a> · <time datetime="{E(meta['date'])}">{E(meta['date'])}</time></p>
  <h1>{E(meta['title'])}</h1>
  <p class="muted lead">{E(desc)}</p>
  <div class="prose">
{journal_md.render(body)}
  </div>
  {language_links(lang, paths)}
  <p><a class="back" href="{list_path(lang)}">{E(s['back'])}</a></p>
</main>
"""
    return out + footer(lang)


def sort_key(item):
    slug, meta = item
    return (meta["date"], meta.get("time", ""), slug)


def build(root, preview=False, warn=None):
    """Return (files {repo-relative path: html}, entries [(loc, lastmod, lang, slug)]).
    Each list page is one entry (slug None); lastmod is the newest post's date.
    Skip unfinished drafts with a warning. If an unfinished article already has a published
    page, fail before the caller can change the generated output."""
    root = Path(root)
    site = origin(root)
    posts = journal_md.load_posts(str(root))
    files, entries = {}, []
    by_lang = {lang: [] for lang in journal_md.LANGS}
    warn = warn or (lambda msg: print(msg, file=sys.stderr))
    for slug, langs in posts.items():
        # Archived articles predate the 12-edition policy.
        legacy = slug in LEGACY_POSTS
        if not legacy and not preview:
            try:
                journal_md.validate_editions(langs)
            except ValueError as exc:
                if any((root / file_of(post_path(lang, slug))).is_file() for lang in journal_md.LANGS):
                    raise ValueError(f"{slug} already has published pages: {exc}") from exc
                warn(f"journal: skipped {slug} (not ready to publish: {exc})")
                continue
        paths = {lang: post_path(lang, slug) for lang in langs}
        for lang, (meta, body) in langs.items():
            for k in ("title", "date", "description"):
                if not meta.get(k):
                    raise ValueError("content/journal/%s/%s.md: front matter '%s' missing" % (slug, lang, k))
            files[file_of(paths[lang])] = render_post(lang, slug, meta, body, paths, site)
            by_lang[lang].append((slug, meta))
            entries.append((site + paths[lang], meta["date"], lang, slug))
    paths = {lang: list_path(lang) for lang, posts in by_lang.items()
             if posts or lang in journal_md.LEGACY_LANGS}
    for lang, path in paths.items():
        ordered = sorted(by_lang[lang], key=sort_key, reverse=True)
        files[file_of(path)] = render_list(lang, site, ordered, paths)
        lastmod = ordered[0][1]["date"] if ordered else None
        entries.append((site + path, lastmod, lang, None))
    return files, entries


def sitemap_block(loc, lastmod, slug, entries, site):
    paths = {lang: url[len(site):] for url, _, lang, article in entries if article == slug}
    alts = alternates(paths, site)
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


def stale_pages(root, files):
    for base in journal_paths():
        folder = root / base
        for page in (*folder.glob("index.html"), *folder.glob("*/index.html")):
            if page.relative_to(root).as_posix() not in files:
                yield page



def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(HERE.parent))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", action="store_true", help="include draft articles in a separate preview root")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    if a.preview and root == HERE.parent:
        ap.error("--preview requires a separate --root")
    site = origin(root)
    if not site:
        print("CNAME missing: site origin unknown")
        return 1
    try:
        files, entries = build(root, preview=a.preview)
    except ValueError as exc:
        print(f"journal: {exc}", file=sys.stderr)
        return 1
    sm = sitemap_text(root, entries, site)
    if a.check:
        stale = [rel for rel, text in files.items()
                 if not (root / rel).is_file() or (root / rel).read_text(encoding="utf-8") != text]
        stale.extend(page.relative_to(root).as_posix() for page in stale_pages(root, files))
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
    for page in stale_pages(root, files):
        page.unlink()
    (root / "sitemap.xml").write_text(sm, encoding="utf-8")
    print("journal: wrote %d pages" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
