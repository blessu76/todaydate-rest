"""Stdlib helpers for the 오늘 어때 journal: front matter + a small Markdown subset.

Subset: paragraphs, ## / ### headings, `- ` lists, `1. ` lists, **bold**, *italic*, `code`, [links](url).
"""
from datetime import date
import html
import os
import re

# ipe_web_kit v0.9.3 languages.SUPPORTED (BCP 47); URL folders are lowercase.
LANGS = ("en", "ko", "ja", "zh-Hant", "es", "pt-BR", "fr", "de", "id", "th", "vi", "tr")
LEGACY_LANGS = ("en", "ko")


def validate_required_front_matter(meta, source, *, require_date=True):
    """Require the metadata used to build a page. Queued drafts get their date at publication."""
    for key in ("title", "date", "description"):
        if key == "date" and not require_date:
            continue
        if not meta.get(key):
            raise ValueError(f"{source}: front matter '{key}' missing")


def validate_editions(editions):
    missing = set(LANGS) - editions.keys()
    if missing:
        raise ValueError("missing journal editions: " + ", ".join(sorted(missing)))
    for lang in LANGS:
        meta, _ = editions[lang]
        if meta.get("lang") != lang or meta.get("copy_review") != "iris":
            raise ValueError(f"{lang}: language and Iris copy review are required")
        try:
            date.fromisoformat(meta.get("copy_review_date", ""))
        except ValueError as exc:
            raise ValueError(f"{lang}: copy_review_date must be a calendar date") from exc


def parse(text):
    """Split `---` front matter (flat `key: value`, optional quotes) from the body. Returns (meta, body)."""
    m = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.S)
    if not m:
        raise ValueError("missing front matter")
    meta = {}
    for line in m.group(1).split("\n"):
        if not line.strip():
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        meta[k.strip()] = v
    return meta, m.group(2).strip() + "\n"


SAFE_SCHEMES = ("http", "https", "mailto")


def _link(m):
    """링크 하나 -> <a>. scheme 은 http·https·mailto 만(상대경로는 허용), 그 밖(javascript: data: …)은 글자만 남긴다."""
    label, raw = m.group(1), html.unescape(m.group(2))  # inline() 이 이미 escape 했으니 되돌려 한 번만 escape 한다
    probe = re.sub(r"[\x00-\x20\x7f]", "", raw)
    sm = re.match(r"([A-Za-z][A-Za-z0-9+.\-]*):", probe)
    if sm and sm.group(1).lower() not in SAFE_SCHEMES:
        return label
    return f'<a href="{html.escape(raw, quote=True)}">{label}</a>'


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _link, s)
    return s


def render(body):
    """Markdown subset -> HTML fragment (no wrapper)."""
    out, para, lst = [], [], None

    def flush_para():
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    def flush_list():
        nonlocal lst
        if lst:
            tag, items = lst
            out.append(f"<{tag}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{tag}>")
            lst = None

    for line in body.split("\n"):
        s = line.rstrip()
        mh = re.match(r"(#{2,3})\s+(.*)", s)
        mu = re.match(r"-\s+(.*)", s)
        mo = re.match(r"\d+\.\s+(.*)", s)
        if not s:
            flush_para()
            flush_list()
        elif mh:
            flush_para()
            flush_list()
            n = len(mh.group(1))
            out.append(f"<h{n}>{inline(mh.group(2))}</h{n}>")
        elif mu or mo:
            flush_para()
            tag = "ul" if mu else "ol"
            if lst and lst[0] != tag:
                flush_list()
            lst = lst or (tag, [])
            lst[1].append((mu or mo).group(1))
        else:
            flush_list()
            para.append(s.strip())
    flush_para()
    flush_list()
    return "\n".join(out)


def load_posts(root):
    """Return {slug: {lang: (meta, body)}} from content/journal/<slug>/<lang>.md."""
    base = os.path.join(root, "content", "journal")
    posts = {}
    if not os.path.isdir(base):
        return posts
    for slug in sorted(os.listdir(base)):
        d = os.path.join(base, slug)
        if not os.path.isdir(d):
            continue
        for lang in LANGS:
            f = os.path.join(d, lang + ".md")
            if os.path.isfile(f):
                with open(f, encoding="utf-8") as fh:
                    posts.setdefault(slug, {})[lang] = parse(fh.read())
    return posts
