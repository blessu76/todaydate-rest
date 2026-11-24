"""Preview card illustration: check_site catches missing srcset files and unsafe <img> markup."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import check_site  # noqa: E402

GOOD_IMG = ('<img src="/a/p-640.webp?v=1" srcset="/a/p-640.webp?v=1 640w, /a/p-1200.webp?v=1 1200w" '
            'width="1200" height="750" alt="">')


def page(img, source='<source type="image/avif" srcset="/a/p-640.avif?v=1 640w">'):
    return ('<!doctype html><html lang="en"><body><article id="preview">'
            '<div class="art" aria-hidden="true"><picture>%s%s</picture></div></article></body></html>' % (source, img))


class PreviewArtTest(unittest.TestCase):
    def errors(self, html, files=("a/p-640.webp", "a/p-1200.webp", "a/p-640.avif")):
        with tempfile.TemporaryDirectory() as d:
            for f in files:
                (Path(d) / f).parent.mkdir(parents=True, exist_ok=True)
                (Path(d) / f).write_bytes(b"x")
            (Path(d) / "index.html").write_text(html, encoding="utf-8")
            errs = []
            check_site.check_links(d, ["index.html"], errs)
            check_site.check_preview_art(d, ["index.html"], errs)
            return errs

    def test_good_markup_passes(self):
        self.assertEqual(self.errors(page(GOOD_IMG)), [])

    def test_missing_srcset_file_is_a_broken_link(self):
        errs = self.errors(page(GOOD_IMG), files=("a/p-640.webp", "a/p-640.avif"))
        self.assertTrue(any("p-1200.webp" in e for e in errs), errs)

    def test_alt_size_avif_and_cache_buster_are_required(self):
        bad = '<img src="/a/p-640.webp" alt="scene">'
        errs = self.errors(page(bad, source=""))
        for needle in ('alt=""', "width/height", "image/avif", "cache-buster"):
            self.assertTrue(any(needle in e for e in errs), (needle, errs))

    def test_non_16_10_size_is_rejected(self):
        errs = self.errors(page(GOOD_IMG.replace('height="750"', 'height="800"')))
        self.assertTrue(any("16:10" in e for e in errs), errs)

    def test_every_landing_page_has_valid_art(self):
        pages = check_site.iter_pages(ROOT)
        errs = []
        check_site.check_preview_art(ROOT, pages, errs)
        self.assertEqual(errs, [])
        with_preview = [p for p in pages if 'id="preview"' in (ROOT / p).read_text(encoding="utf-8")]
        self.assertEqual(len(with_preview), 15)


if __name__ == "__main__":
    unittest.main()
