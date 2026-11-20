"""Journal helpers: front matter, the Markdown subset, and the list/article builder. Stdlib only."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_journal  # noqa: E402
import journal_md  # noqa: E402


class ParseTest(unittest.TestCase):
    def test_front_matter_and_body(self):
        meta, body = journal_md.parse('---\ntitle: "A: B"\ndate: 2026-11-20\n---\nHello\n')
        self.assertEqual(meta["title"], "A: B")
        self.assertEqual(meta["date"], "2026-11-20")
        self.assertEqual(body, "Hello\n")

    def test_missing_front_matter_raises(self):
        with self.assertRaises(ValueError):
            journal_md.parse("no front matter")


class RenderTest(unittest.TestCase):
    def test_headings_lists_and_inline(self):
        html = journal_md.render("## Head\n\n- one **bold**\n- two `x<y`\n\n1. first\n2. [link](https://e.x/)\n\nPara *em*.")
        self.assertIn("<h2>Head</h2>", html)
        self.assertIn("<ul><li>one <strong>bold</strong></li><li>two <code>x&lt;y</code></li></ul>", html)
        self.assertIn('<ol><li>first</li><li><a href="https://e.x/">link</a></li></ol>', html)
        self.assertIn("<p>Para <em>em</em>.</p>", html)

    def test_text_is_escaped(self):
        self.assertIn("&lt;script&gt;", journal_md.render("<script>"))


def write_post(root, slug, lang, title, date, time, langs_present=None):
    d = Path(root) / "content" / "journal" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{lang}.md").write_text(
        f'---\ntitle: {title}\ndate: {date}\ntime: "{time}"\nslug: {slug}\nlang: {lang}\n'
        f'description: Desc {slug}\n---\n\n## Part\n\nBody text.\n', encoding="utf-8")


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        root = Path(self.tmp)
        (root / "CNAME").write_text("example.test\n", encoding="utf-8")
        (root / "sitemap.xml").write_text(
            '<?xml version="1.0"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n  <url>\n    <loc>https://example.test/</loc>\n  </url>\n'
            '  <url>\n    <loc>https://example.test/journal/old/</loc>\n  </url>\n</urlset>\n', encoding="utf-8")
        write_post(root, "older", "en", "Older", "2026-11-19", "12:00")
        write_post(root, "older", "ko", "이전", "2026-11-19", "12:00")
        write_post(root, "newer", "en", "Newer", "2026-11-20", "13:00")
        self.root = root

    def test_build_pages_and_order(self):
        files, entries = build_journal.build(self.root)
        self.assertIn("journal/index.html", files)
        self.assertIn("ko/journal/index.html", files)
        self.assertIn("journal/newer/index.html", files)
        self.assertIn("ko/journal/older/index.html", files)
        self.assertNotIn("ko/journal/newer/index.html", files)  # no Korean edition
        en_list = files["journal/index.html"]
        self.assertLess(en_list.index("Newer"), en_list.index("Older"))  # newest first
        self.assertIn('hreflang="ko" href="https://example.test/ko/journal/"', en_list)

    def test_article_alternates_only_when_both_languages(self):
        files, _ = build_journal.build(self.root)
        self.assertNotIn('hreflang="ko"', files["journal/newer/index.html"].split("</head>")[0])
        self.assertIn('hreflang="ko" href="https://example.test/ko/journal/older/"',
                      files["journal/older/index.html"].split("</head>")[0])

    def test_sitemap_replaces_only_journal_blocks(self):
        files, entries = build_journal.build(self.root)
        sm = build_journal.sitemap_text(self.root, entries, "https://example.test")
        self.assertIn("<loc>https://example.test/</loc>", sm)  # non-journal kept
        self.assertNotIn("/journal/old/", sm)  # stale journal entry dropped
        self.assertIn("<loc>https://example.test/journal/newer/</loc>", sm)
        self.assertIn("<loc>https://example.test/ko/journal/older/</loc>", sm)

    def test_missing_front_matter_field_fails(self):
        d = self.root / "content" / "journal" / "bad"
        d.mkdir(parents=True)
        (d / "en.md").write_text("---\ntitle: X\ndate: 2026-11-20\n---\nbody\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            build_journal.build(self.root)


if __name__ == "__main__":
    unittest.main()
