"""Preview card markup and responsive image dimensions."""
import struct
import sys
import tempfile
import unittest
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import check_site  # noqa: E402

GOOD_IMG = ('<img src="/a/p-640.webp?v=1" srcset="/a/p-640.webp?v=1 640w, /a/p-1200.webp?v=1 1200w" '
            'width="1200" height="750" alt="">')
GOOD_SOURCE = '<source type="image/avif" srcset="/a/p-640.avif?v=1 640w">'
LANDING_PAGES = ["index.html"] + [f"{lang}/index.html" for lang in check_site.lang_folders(ROOT)]


def page(img, source=GOOD_SOURCE):
    return ('<!doctype html><html lang="en"><body><article id="preview">'
            '<div class="art" aria-hidden="true"><picture>%s%s</picture></div></article></body></html>' % (source, img))


def boxes(data):
    """Yield ISO BMFF box types and payloads without reading into sibling boxes."""
    offset = 0
    while offset < len(data):
        size, kind = struct.unpack_from(">I4s", data, offset)
        header_size = 8
        if size == 1:
            size, = struct.unpack_from(">Q", data, offset + 8)
            header_size = 16
        elif size == 0:
            size = len(data) - offset
        end = offset + size
        if size < header_size or end > len(data):
            raise ValueError(f"invalid size for {kind!r} box")
        yield kind, data[offset + header_size:end]
        offset = end


def box(data, kind):
    return next(payload for name, payload in boxes(data) if name == kind)


def avif_size(data):
    meta = box(data, b"meta")[4:]  # FullBox version and flags
    properties = box(box(meta, b"iprp"), b"ipco")
    sizes = {struct.unpack_from(">II", payload, 4) for kind, payload in boxes(properties) if kind == b"ispe"}
    # The preview AVIFs are stills with a single image extent.
    if len(sizes) != 1:
        raise ValueError("expected one distinct AVIF image extent")
    return sizes.pop()


def webp_size(data):
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("invalid WebP header")
    kind, length = struct.unpack_from("<4sI", data, 12)
    payload = data[20:20 + length]
    if kind == b"VP8 " and payload[3:6] == b"\x9d\x01\x2a":
        width, height = struct.unpack_from("<HH", payload, 6)
        return width & 0x3fff, height & 0x3fff
    if kind == b"VP8L" and payload[:1] == b"\x2f":
        packed, = struct.unpack_from("<I", payload, 1)
        return (packed & 0x3fff) + 1, ((packed >> 14) & 0x3fff) + 1
    if kind == b"VP8X" and len(payload) == 10:
        return int.from_bytes(payload[4:7], "little") + 1, int.from_bytes(payload[7:10], "little") + 1
    raise ValueError(f"invalid WebP image chunk {kind!r}")


@lru_cache(maxsize=None)
def image_size(path):
    read_size = {".avif": avif_size, ".webp": webp_size}[path.suffix.lower()]
    return read_size(path.read_bytes())


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

    def test_pictureless_art_does_not_capture_following_images(self):
        html = ('<article id="preview"><div class="art"><div></div></div>'
                f'<picture>{GOOD_SOURCE}{GOOD_IMG}</picture></article>')
        errs = self.errors(html)
        self.assertEqual(errs, ["index.html: preview .art needs exactly one <img> (found 0)"])

    def test_nested_div_end_does_not_close_the_art(self):
        html = page(GOOD_IMG).replace("<picture>", "<div></div><picture>")
        self.assertEqual(self.errors(html), [])

    def test_art_outside_preview_is_ignored(self):
        html = page(GOOD_IMG).replace("</body>", f'<div class="art">{GOOD_IMG}</div></body>')
        self.assertEqual(self.errors(html), [])

    def test_every_landing_page_has_valid_art(self):
        for path in LANDING_PAGES:
            with self.subTest(page=path):
                parser = check_site._Collect()
                parser.feed((ROOT / path).read_text(encoding="utf-8"))
                self.assertTrue(parser.has_preview)
        errs = []
        check_site.check_preview_art(ROOT, LANDING_PAGES, errs)
        self.assertEqual(errs, [])

    def test_srcset_widths_match_actual_image_sizes(self):
        for path in LANDING_PAGES:
            parser = check_site._Collect()
            parser.feed((ROOT / path).read_text(encoding="utf-8"))
            for attrs in parser.art_sources + parser.art_imgs:
                for candidate in attrs["srcset"].split(","):
                    with self.subTest(page=path, candidate=candidate.strip()):
                        url, descriptor = candidate.split()
                        self.assertRegex(descriptor, r"^[1-9][0-9]*w$")
                        image_path = unquote(urlsplit(url).path)
                        base = ROOT if image_path.startswith("/") else (ROOT / path).parent
                        asset = base / image_path.lstrip("/")
                        width, height = image_size(asset)
                        self.assertEqual(width, int(descriptor[:-1]))
                        self.assertEqual(width * 10, height * 16)


if __name__ == "__main__":
    unittest.main()
