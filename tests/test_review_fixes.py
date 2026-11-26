"""Pins for the journal publisher review (W1-W8): partial copy review, ordering, cwd-free imports,
kit_lock, journal hreflang/x-default targets, date quoting and STOCK_ALERT on stderr. Stdlib only."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "ops"))
import build_journal  # noqa: E402
import check_site  # noqa: E402
import journal_md  # noqa: E402
import kit_lock  # noqa: E402
import publish_next  # noqa: E402

SITEMAP = ('<?xml version="1.0"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
           'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n  <url>\n    <loc>https://example.test/</loc>\n'
           '  </url>\n</urlset>\n')


def write_edition(root, slug, lang, date="2026-11-26", time="12:00", reviewed=True, title=None):
    d = Path(root) / "content" / "journal" / slug
    d.mkdir(parents=True, exist_ok=True)
    review = "copy_review: iris\ncopy_review_date: 2026-11-26\n" if reviewed else ""
    (d / f"{lang}.md").write_text(
        f'---\ntitle: {title or slug}\ndate: {date}\ntime: "{time}"\nslug: {slug}\nlang: {lang}\n'
        f'{review}description: Desc {slug}\n---\n\n## Part\n\nBody text.\n', encoding="utf-8")


def site_root():
    root = Path(tempfile.mkdtemp())
    (root / "CNAME").write_text("example.test\n", encoding="utf-8")
    (root / "sitemap.xml").write_text(SITEMAP, encoding="utf-8")
    return root


class PartialReviewTest(unittest.TestCase):
    """W1: one unfinished edition must not fail the whole site; that article is skipped with a warning."""

    def setUp(self):
        self.root = site_root()
        for lang in journal_md.LANGS:
            write_edition(self.root, "ready", lang)
        # Iris reviewed only some editions of "partial".
        for i, lang in enumerate(journal_md.LANGS):
            write_edition(self.root, "partial", lang, reviewed=i < 5)
        # "gap" is fully reviewed but one edition is missing.
        for lang in journal_md.LANGS[:-1]:
            write_edition(self.root, "gap", lang)

    def test_partial_review_and_missing_edition_are_skipped_with_a_warning(self):
        warnings = []
        files, entries = build_journal.build(self.root, warn=warnings.append)
        self.assertIn("journal/ready/index.html", files)
        self.assertFalse(any("/partial/" in f or "/gap/" in f for f in files))
        self.assertFalse(any(slug in ("partial", "gap") for *_, slug in entries))
        self.assertEqual(len(warnings), 2)
        self.assertTrue(any("partial" in w and "copy review" in w.lower() for w in warnings), warnings)
        self.assertTrue(any("gap" in w and "missing journal editions" in w for w in warnings), warnings)

    def test_default_warning_goes_to_stderr(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            build_journal.build(self.root)
        self.assertIn("journal: skipped partial", err.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_write_then_check_stays_green(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(build_journal.main(["--root", str(self.root)]), 0)
            self.assertEqual(build_journal.main(["--root", str(self.root), "--check"]), 0)
        self.assertTrue((self.root / "journal/ready/index.html").is_file())
        self.assertFalse((self.root / "journal/partial").exists())

    def test_preview_still_renders_unready_articles(self):
        files, _ = build_journal.build(self.root, preview=True, warn=self.fail)
        self.assertIn("journal/partial/index.html", files)
        self.assertIn("journal/gap/index.html", files)


class OrderingTest(unittest.TestCase):
    """W2: list order is (date, time, slug) newest first; queue order is (number, name)."""

    def test_same_date_and_time_breaks_ties_by_slug(self):
        root = site_root()
        for slug in ("bbb", "aaa", "ccc"):
            for lang in journal_md.LANGS:
                write_edition(root, slug, lang, title=f"T-{slug}")
        for lang in journal_md.LANGS:
            write_edition(root, "later", lang, time="13:00", title="T-later")
        first = build_journal.build(root)[0]["journal/index.html"]
        order = sorted(("T-later", "T-aaa", "T-bbb", "T-ccc"), key=first.index)
        self.assertEqual(order, ["T-later", "T-ccc", "T-bbb", "T-aaa"])
        self.assertEqual(build_journal.build(root)[0]["journal/index.html"], first)

    def test_load_posts_is_sorted_by_slug(self):
        root = site_root()
        for slug in ("zeta", "alpha", "mid"):
            write_edition(root, slug, "en")
        self.assertEqual(list(journal_md.load_posts(str(root))), ["alpha", "mid", "zeta"])

    def test_queue_ties_and_unnumbered_folders(self):
        q = tempfile.mkdtemp()
        for name in ("02-b", "02-a", "10-x", "1-first", "readme", ".published"):
            os.makedirs(os.path.join(q, name))
        self.assertEqual(publish_next.queue_folders(q), ["1-first", "02-a", "02-b", "10-x"])


class ImportPathTest(unittest.TestCase):
    """W3: publish_next imports journal_md from its own location, whatever the cwd."""

    def test_check_queue_runs_from_another_cwd(self):
        q, elsewhere = tempfile.mkdtemp(), tempfile.mkdtemp()
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        r = subprocess.run([sys.executable, str(ROOT / "ops" / "publish_next.py"), "--queue", q, "--check-queue"],
                           cwd=elsewhere, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertNotIn("ModuleNotFoundError", r.stderr)
        self.assertIn("STOCK_ALERT", r.stderr)


class DateQuotingTest(unittest.TestCase):
    """W7: date is written bare and time quoted (HH:MM), and parse reads both quoted or bare the same."""

    def test_parse_accepts_quoted_and_bare_values(self):
        for date, time in (("2026-11-21", '"14:05"'), ('"2026-11-21"', "14:05"), ("'2026-11-21'", "'14:05'")):
            meta, _ = journal_md.parse(f"---\ntitle: T\ndate: {date}\ntime: {time}\n---\nbody\n")
            self.assertEqual((meta["date"], meta["time"]), ("2026-11-21", "14:05"), (date, time))

    def test_stamp_round_trips_through_parse(self):
        text = "---\ntitle: T\ndescription: D\n---\n\nBody\n"
        meta, _ = journal_md.parse(publish_next.stamp(text, "2026-11-21", "09:30"))
        self.assertEqual((meta["date"], meta["time"]), ("2026-11-21", "09:30"))


class StockAlertTest(unittest.TestCase):
    """W8: every STOCK_ALERT line is on stderr, never stdout."""

    def run_quiet(self, fn, *args, **kw):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = fn(*args, **kw)
        return code, out.getvalue(), err.getvalue()

    def test_empty_queue_check(self):
        code, out, err = self.run_quiet(publish_next.check_queue, tempfile.mkdtemp())
        self.assertEqual(code, 3)
        self.assertIn("STOCK_ALERT", err)
        self.assertNotIn("STOCK_ALERT", out)

    def test_low_stock_check(self):
        q = tempfile.mkdtemp()
        os.makedirs(os.path.join(q, "01-only"))
        code, out, err = self.run_quiet(publish_next.check_queue, q)
        self.assertIn("STOCK_ALERT", err)
        self.assertNotIn("STOCK_ALERT", out)

    def test_empty_queue_publish(self):
        code, out, err = self.run_quiet(publish_next.publish, tempfile.mkdtemp(), "2026-11-21", "12:00",
                                        dry_run=True, pull=False)
        self.assertEqual(code, 3)
        self.assertIn("STOCK_ALERT", err)
        self.assertNotIn("STOCK_ALERT", out)


class KitLockTest(unittest.TestCase):
    """W4: kit_lock check against a fake installed kit (the real kit is private and not in the repo)."""

    TAG, COMMIT = "v9.9.9", "a" * 40

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.pkg = self.root / kit_lock.PKG
        self.pkg.mkdir(parents=True)
        (self.pkg / "KIT_VERSION").write_text(f"{self.TAG} {self.COMMIT}\n", encoding="utf-8")
        (self.pkg / "MANIFEST.sha256").write_text("deadbeef  a.css\n", encoding="utf-8")
        self.set_verify(0)
        self.write_lock()

    def write_lock(self, **override):
        lock = {"tag": self.TAG, "commit": self.COMMIT,
                "manifest_sha256": hashlib.sha256((self.pkg / "MANIFEST.sha256").read_bytes()).hexdigest()}
        lock.update(override)
        body = "# test lock\n" + "".join(f"{k}={v}\n" for k, v in lock.items() if v is not None)
        (self.root / kit_lock.LOCK).write_text(body, encoding="utf-8")

    def set_verify(self, code):
        (self.pkg / "vendor.py").write_text(
            f"import sys\nif {code}:\n    sys.stderr.write('a.css changed\\n')\nsys.exit({code})\n", encoding="utf-8")

    def test_matching_kit_is_ok(self):
        self.assertEqual(kit_lock.problems(self.root), [])
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(kit_lock.main(["--root", str(self.root), "check"]), 0)
        self.assertIn("ipe_web_kit: OK", out.getvalue())

    def test_missing_lock_or_key_stops(self):
        self.write_lock(manifest_sha256=None)
        with self.assertRaisesRegex(SystemExit, "missing manifest_sha256"):
            kit_lock.read_lock(self.root)
        (self.root / kit_lock.LOCK).unlink()
        with self.assertRaisesRegex(SystemExit, "not found"):
            kit_lock.read_lock(self.root)

    def test_not_installed(self):
        (self.pkg / "KIT_VERSION").unlink()
        self.assertEqual(kit_lock.problems(self.root), ["%s is not installed" % kit_lock.PKG])

    def test_version_mismatch(self):
        self.write_lock(tag="v0.0.1")
        self.assertTrue(any("differs from the lock" in p for p in kit_lock.problems(self.root)))

    def test_manifest_mismatch(self):
        self.write_lock(manifest_sha256="0" * 64)
        self.assertIn("kit manifest hash differs from the lock", kit_lock.problems(self.root))

    def test_changed_files_and_missing_vendor_script(self):
        self.set_verify(1)
        self.assertTrue(any("a.css changed" in p for p in kit_lock.problems(self.root)))
        (self.pkg / "vendor.py").unlink()
        self.assertIn("%s/vendor.py missing" % kit_lock.PKG, kit_lock.problems(self.root))

    def test_check_exits_1_with_help_on_stderr(self):
        self.write_lock(manifest_sha256="0" * 64)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(kit_lock.main(["--root", str(self.root), "check"]), 1)
        self.assertIn("kit_lock: kit manifest hash differs", err.getvalue())
        self.assertIn("kit_lock.py sync", err.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_repo_lock_has_every_key(self):
        lock = kit_lock.read_lock(ROOT)
        self.assertRegex(lock["tag"], r"^v\d+\.\d+\.\d+$")
        self.assertRegex(lock["commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(lock["manifest_sha256"], r"^[0-9a-f]{64}$")


class JournalHreflangTest(unittest.TestCase):
    """W5/W6: each journal alternate points at the same article in its own language; x-default at English."""

    def setUp(self):
        self.root = site_root()
        for lang in journal_md.LANGS:
            write_edition(self.root, "ready", lang)
        files, _ = build_journal.build(self.root)
        for rel, text in files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        self.page = "ko/journal/ready/index.html"
        self.origin = "https://example.test"
        self.expected = {check_site.tag_for(f): f for f in check_site.STANDARD_FOLDERS}

    def errors(self):
        errs = []
        check_site.check_hreflang(self.root, self.origin, [self.page], list(check_site.STANDARD_FOLDERS), errs)
        return [e for e in errs if not e.startswith("language folders")]

    def edit(self, old, new):
        p = self.root / self.page
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text)
        p.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_built_article_passes(self):
        self.assertEqual(self.errors(), [])

    def test_alternates_are_not_self_only(self):
        head = (self.root / self.page).read_text(encoding="utf-8").split("</head>")[0]
        for lang in journal_md.LANGS:
            href = self.origin + build_journal.post_path(lang, "ready")
            self.assertIn(f'hreflang="{lang}" href="{href}"', head)
        self.assertIn(f'hreflang="x-default" href="{self.origin}/journal/ready/"', head)

    def test_alternate_pointing_at_another_article_fails(self):
        for lang in journal_md.LANGS:
            write_edition(self.root, "other", lang)
        (self.root / "ja/journal/other").mkdir(parents=True)
        (self.root / "ja/journal/other/index.html").write_text("<html></html>", encoding="utf-8")
        self.edit('hreflang="ja" href="https://example.test/ja/journal/ready/"',
                  'hreflang="ja" href="https://example.test/ja/journal/other/"')
        self.assertTrue(any("hreflang ja points to" in e for e in self.errors()), self.errors())

    def test_x_default_must_be_the_english_article(self):
        self.edit('hreflang="x-default" href="https://example.test/journal/ready/"',
                  'hreflang="x-default" href="https://example.test/ko/journal/ready/"')
        self.assertTrue(any("hreflang x-default points to" in e for e in self.errors()), self.errors())

    def test_duplicate_code_fails(self):
        self.edit('<link rel="alternate" hreflang="ja"',
                  '<link rel="alternate" hreflang="ja" href="https://example.test/ja/journal/ready/">'
                  '<link rel="alternate" hreflang="ja"')
        self.assertTrue(any("listed more than once" in e for e in self.errors()), self.errors())


if __name__ == "__main__":
    unittest.main()
