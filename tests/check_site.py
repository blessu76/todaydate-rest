#!/usr/bin/env python3
"""Site consistency check for the static site — stdlib only. Exit 0 = consistent, exit 1 = something is off.

  python3 tests/check_site.py                 # check the repo this file belongs to
  python3 tests/check_site.py --root <dir>    # check another tree (used for fixtures)

Checks (each failure prints its reason):
  1. every <loc> in sitemap.xml maps to a file inside the tree (…/index.html, or a .html file).
  2. every index.html page (except design/ and dot-dirs) is listed in sitemap.xml.
  3. every page's hreflang alternates match the language folders (the 12 standard languages, as BCP 47 tags:
     zh-hans -> zh-Hans, zh-hant -> zh-Hant, pt-br -> pt-BR), include x-default, point at their
     own folder, and <html lang> of a language page equals its tag.
     Ended languages (zh-hans, ar) are exempt: they must be noindex, link to /en/, carry no
     hreflang and not be in sitemap.xml.
  4. every relative or root-relative internal href/src resolves to a file in the tree.

Pages are index.html files; design/ mockups are not site pages and are skipped.
The site origin is read from CNAME (https://<host>).
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
SKIP_DIRS = {".git", "design", "node_modules"}
LANG_RE = re.compile(r"^[a-z]{2}(?:-[A-Za-z0-9]{2,8})?$")
EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel", "data", "javascript", "sms"}
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
# Folder names are lowercase URL paths; the language tags used in hreflang and
# <html lang> are BCP 47 (script subtags capitalised, region uppercase).
BCP47_TAG = {"zh-hans": "zh-Hans", "zh-hant": "zh-Hant", "pt-br": "pt-BR"}
# Company standard (kit-0029 / ADR-0087): 12 languages, as folders. Ended languages keep their
# pages (not deleted) but are out of the selector, hreflang and sitemap; they must be noindex
# and point readers to /en/.
STANDARD_FOLDERS = ["en", "ko", "ja", "zh-hant", "es", "pt-br", "fr", "de", "id", "th", "vi", "tr"]
ENDED_FOLDERS = {"zh-hans", "ar", "ru", "hi"}
# Journal pages (journal/…, ko/journal/…) exist only in English and Korean (see scripts/build_journal.py).
JOURNAL_TAGS = {"en", "ko"}


def tag_for(folder):
    """Language folder ('pt-br') -> BCP 47 tag ('pt-BR')."""
    return BCP47_TAG.get(folder, folder)


def is_journal(page):
    """'journal/x/index.html' or 'ko/journal/x/index.html' (any journal page, list or article)."""
    parts = Path(page).parts
    return parts[:1] == ("journal",) or parts[:2] == ("ko", "journal")


class _Collect(HTMLParser):
    """Collects link[rel=alternate][hreflang], <html lang>, every href/src/srcset value and the preview art."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.alternates = []  # (hreflang, href)
        self.html_lang = None  # value of <html lang>
        self.refs = []  # href/src values
        self.noindex = False  # <meta name="robots" content="...noindex...">
        self.has_preview = False  # <article id="preview">
        self._preview_depth = 0  # open articles starting with article#preview
        self._art_depth = 0  # open divs starting with div.art inside the preview
        self.art_imgs = []  # attrs of <img> inside .art
        self.art_sources = []  # attrs of <source> inside .art

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and "lang" in a:
            self.html_lang = a["lang"].strip()
        for key in ("href", "src"):
            if key in a:
                self.refs.append(a[key].strip())
        if "srcset" in a:
            self.refs.extend(c.split()[0] for c in a["srcset"].split(",") if c.strip())
        if tag == "article" and a.get("id") == "preview":
            self.has_preview = True
            self._preview_depth += 1
        elif tag == "article" and self._preview_depth:
            self._preview_depth += 1
        if tag == "div" and self._preview_depth and (self._art_depth or "art" in a.get("class", "").split()):
            self._art_depth += 1
        if self._art_depth:
            if tag == "img":
                self.art_imgs.append(a)
            elif tag == "source":
                self.art_sources.append(a)
        if tag == "meta" and a.get("name", "").lower() == "robots" and "noindex" in a.get("content", "").lower():
            self.noindex = True
        if tag == "link" and a.get("rel", "").lower() == "alternate" and "hreflang" in a:
            self.alternates.append((a["hreflang"].strip(), a.get("href", "").strip()))

    def handle_endtag(self, tag):
        if tag == "div" and self._art_depth:
            self._art_depth -= 1
        if tag == "article" and self._preview_depth:
            self._preview_depth -= 1
            if not self._preview_depth:
                self._art_depth = 0


def site_origin(root):
    try:
        host = (Path(root) / "CNAME").read_text(encoding="utf-8").strip()
    except OSError:
        host = ""
    return "https://%s" % host if host else ""


def iter_pages(root):
    """index.html files as POSIX paths relative to root."""
    out = []
    for p in sorted(Path(root).rglob("index.html")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        out.append(rel.as_posix())
    return out


def url_to_file(url, origin):
    """'https://host/a/b/' -> 'a/b/index.html'; '/a.html' -> 'a.html'; None if not a site URL."""
    if url.startswith(("http://", "https://")):
        if not origin or not url.startswith(origin):
            return None
        url = url[len(origin):] or "/"
    path = unquote(urlsplit(url).path)
    if not path.startswith("/"):
        return None
    path = path.lstrip("/")
    if path == "" or path.endswith("/"):
        return path + "index.html"
    if path.endswith(".html"):
        return path
    return path + "/index.html"


def check_sitemap(root, origin, pages, errs):
    sm = Path(root) / "sitemap.xml"
    if not sm.is_file():
        errs.append("sitemap.xml: missing")
        return
    try:
        tree = ET.parse(sm)
    except ET.ParseError as ex:
        errs.append("sitemap.xml: parse error: %s" % ex)
        return
    listed = set()
    for loc in tree.iter(SITEMAP_NS + "loc"):
        url = (loc.text or "").strip()
        f = url_to_file(url, origin)
        if f is None:
            errs.append("sitemap.xml: <loc> not on %s: %s" % (origin or "this site", url))
            continue
        if not (Path(root) / f).is_file():
            errs.append("sitemap.xml: <loc> %s -> %s not found in repo" % (url, f))
        listed.add(f)
    for page in pages:
        if Path(page).parts[0] in ENDED_FOLDERS:
            if page in listed:
                errs.append("%s: ended language must not be listed in sitemap.xml" % page)
            continue
        if page not in listed:
            errs.append("%s: not listed in sitemap.xml" % page)


def lang_folders(root):
    """Top-level language folders that contain an index.html."""
    return sorted(
        p.name for p in Path(root).iterdir()
        if p.is_dir() and LANG_RE.match(p.name) and (p / "index.html").is_file()
    )


def check_hreflang(root, origin, pages, langs, errs):
    # hreflang codes must be the BCP 47 tag of each language folder; each code's
    # href must point at that folder; <html lang> of a language page must match it too.
    active = [f for f in langs if f not in ENDED_FOLDERS]
    if sorted(active) != sorted(STANDARD_FOLDERS):
        errs.append("language folders %s do not match the 12 standard languages %s"
                    % (sorted(active), sorted(STANDARD_FOLDERS)))
    expected = {tag_for(f): f for f in active}
    for page in pages:
        parser = _Collect()
        parser.feed((Path(root) / page).read_text(encoding="utf-8"))
        top = Path(page).parts[0] if len(Path(page).parts) > 1 else None
        if top in ENDED_FOLDERS:
            if parser.alternates:
                errs.append("%s: ended language must not carry hreflang alternates" % page)
            if not parser.noindex:
                errs.append("%s: ended language must be noindex" % page)
            if not any(r.startswith("/en/") for r in parser.refs):
                errs.append("%s: ended language must link to /en/" % page)
            continue
        alts = parser.alternates
        codes = [h for h, _ in alts]
        if "x-default" not in codes:
            errs.append("%s: hreflang x-default missing" % page)
        got = set(codes) - {"x-default"}
        # 저널(journal/, ko/journal/)은 영어·한국어 두 벌만 있다 — 나머지 언어는 번역 전까지 만들지 않는다.
        want = {c: f for c, f in expected.items() if c in JOURNAL_TAGS} if is_journal(page) else expected
        if got != set(want):
            errs.append("%s: hreflang %s does not match language folders %s"
                        % (page, sorted(got), sorted(want)))
        for code, href in alts:
            f = url_to_file(href, origin)
            if f is None:
                errs.append("%s: hreflang %s href not a site URL: %s" % (page, code, href))
                continue
            if is_journal(page):
                # journal: en -> journal/…, ko -> ko/journal/… (x-default = en)
                want_prefix = {"en": "journal/", "ko": "ko/journal/", "x-default": "journal/"}.get(code)
                if want_prefix and not f.startswith(want_prefix):
                    errs.append("%s: hreflang %s points to %s (expected %s…)" % (page, code, href, want_prefix))
            elif code in expected and not f.startswith(expected[code] + "/"):
                errs.append("%s: hreflang %s points to %s (expected folder %s)"
                            % (page, code, href, expected[code]))
            if not (Path(root) / f).is_file():
                errs.append("%s: hreflang %s -> %s not found" % (page, code, f))
        folder = Path(page).parts[0] if len(Path(page).parts) > 1 else None
        if folder in expected and parser.html_lang != tag_for(folder):
            errs.append("%s: <html lang> %r does not match folder tag %r"
                        % (page, parser.html_lang, tag_for(folder)))


def check_links(root, pages, errs):
    for page in pages:
        parser = _Collect()
        parser.feed((Path(root) / page).read_text(encoding="utf-8"))
        base = Path(page).parent
        for ref in parser.refs:
            if not ref or ref.startswith("#"):
                continue
            parts = urlsplit(ref)
            if parts.scheme.lower() in EXTERNAL_SCHEMES or parts.netloc:
                continue  # external or absolute-host; origin links are covered by hreflang/sitemap checks
            target = unquote(parts.path)
            if not target:
                continue  # query-only or fragment-only
            if target.startswith("/"):
                rel = Path(target.lstrip("/"))
            else:
                rel = (base / target)
            rel = Path(*[x for x in rel.parts if x not in ("", ".")]) if rel.parts else Path(".")
            full = Path(root) / rel
            if target.endswith("/") or full.is_dir():
                ok = (full / "index.html").is_file()
                where = (rel / "index.html").as_posix()
            else:
                ok = full.is_file()
                where = rel.as_posix()
            if not ok:
                errs.append("%s: broken link %r -> %s" % (page, ref, where))


def check_preview_art(root, pages, errs):
    """Landing preview cards carry one decorative, sized, cache-busted illustration (AVIF + WebP)."""
    for page in pages:
        parser = _Collect()
        parser.feed((Path(root) / page).read_text(encoding="utf-8"))
        if not parser.has_preview:
            continue
        if len(parser.art_imgs) != 1:
            errs.append("%s: preview .art needs exactly one <img> (found %d)" % (page, len(parser.art_imgs)))
            continue
        img = parser.art_imgs[0]
        if img.get("alt", None) != "":
            errs.append("%s: preview art is decorative (aria-hidden) and needs alt=\"\"" % page)
        if not (img.get("width") and img.get("height")):
            errs.append("%s: preview art <img> needs width/height to avoid layout shift" % page)
        elif not (img["width"].isdigit() and img["height"].isdigit()
                  and int(img["width"]) * 10 == int(img["height"]) * 16):
            errs.append("%s: preview art <img> width/height must be 16:10 like the .art box" % page)
        if not any(source.get("type") == "image/avif" for source in parser.art_sources):
            errs.append("%s: preview art needs an image/avif <source>" % page)
        urls = [img.get("src", "")] + [c.split()[0] for c in img.get("srcset", "").split(",") if c.strip()]
        for u in urls:
            if "?v=" not in u:
                errs.append("%s: preview art %r lacks a ?v= cache-buster" % (page, u))


def run(root):
    root = Path(root).resolve()
    origin = site_origin(root)
    pages = iter_pages(root)
    errs = []
    if not origin:
        errs.append("CNAME: missing or empty (site origin unknown)")
    check_sitemap(root, origin, pages, errs)
    check_hreflang(root, origin, pages, lang_folders(root), errs)
    check_links(root, pages, errs)
    check_preview_art(root, pages, errs)
    return errs, pages


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(HERE.parent), help="site tree to check (default: repo root)")
    args = ap.parse_args(argv)
    errs, pages = run(args.root)
    if errs:
        print("check_site: FAIL (%d problem%s)" % (len(errs), "" if len(errs) == 1 else "s"))
        for e in errs:
            print("  - " + e)
        return 1
    print("check_site: OK (%d page%s)" % (len(pages), "" if len(pages) == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
