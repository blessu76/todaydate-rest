"""publish_next helpers: queue order, date/time stamping, 12 editions. No git, no network."""
from contextlib import redirect_stderr, redirect_stdout
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import publish_next  # noqa: E402

SAMPLE = '---\ntitle: T\ndescription: D\nslug: s\nlang: en\ncopy_review: iris\ncopy_review_date: 2026-11-26\n---\n\nBody\n'


class StampTest(unittest.TestCase):
    def test_inserts_date_and_time_after_title(self):
        out = publish_next.stamp(SAMPLE, "2026-11-21", "14:05")
        self.assertIn('title: T\ndate: 2026-11-21\ntime: "14:05"\ndescription: D', out)
        self.assertTrue(out.endswith("\n---\n\nBody\n"))

    def test_replaces_existing_date_and_time(self):
        text = SAMPLE.replace("title: T\n", 'title: T\ndate: 2000-01-01\ntime: "01:01"\n')
        out = publish_next.stamp(text, "2026-11-21", "14:05")
        self.assertEqual(sum(line.startswith("date:") for line in out.splitlines()), 1)
        self.assertNotIn("2000-01-01", out)
        self.assertIn('time: "14:05"', out)


class QueueTest(unittest.TestCase):
    def setUp(self):
        self.q = tempfile.mkdtemp()
        for name in ("02-b", "01-a", "notes", ".published"):
            os.makedirs(os.path.join(self.q, name))

    def test_front_of_queue_is_lowest_number(self):
        os.makedirs(os.path.join(self.q, "100-later"))
        os.makedirs(os.path.join(self.q, "9-next"))
        self.assertEqual(publish_next.next_folder(self.q), "01-a")
        self.assertEqual(publish_next.queue_folders(self.q), ["01-a", "02-b", "9-next", "100-later"])

    def test_empty_queue_returns_none(self):
        empty = tempfile.mkdtemp()
        self.assertIsNone(publish_next.next_folder(empty))

    def test_editions_need_all_languages_and_copy_review(self):
        folder = os.path.join(self.q, "01-a")
        Path(folder, "en.md").write_text(SAMPLE, encoding="utf-8")
        with self.assertRaises(FileNotFoundError):
            publish_next.editions(folder)
        for lang in publish_next.journal_md.LANGS:
            Path(folder, f"{lang}.md").write_text(SAMPLE.replace("lang: en", f"lang: {lang}"), encoding="utf-8")
        self.assertEqual([lang for lang, _ in publish_next.editions(folder)], list(publish_next.journal_md.LANGS))
        Path(folder, "en.md").write_text(SAMPLE.replace("copy_review: iris", "copy_review: pending"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Iris"):
            publish_next.editions(folder)

    def test_queue_check_reports_an_unreviewed_batch_without_consuming_it(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(publish_next.check_queue(self.q), 5)
        self.assertIn("01-a: 발행 준비 미완료", stderr.getvalue())
        self.assertIn("02-b: 발행 준비 미완료", stderr.getvalue())
        self.assertEqual(publish_next.queue_folders(self.q), ["01-a", "02-b"])


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.x",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.x"}).stdout.strip()


class PublishFlowTest(unittest.TestCase):
    """publish() 흐름 — 임시 git 저장소 + bare origin, push 꺼짐, 빌드·검사는 가짜 스크립트."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.origin = root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        self.repo = root / "repo"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.repo)], check=True, capture_output=True)
        git(self.repo, "checkout", "-q", "-B", "main")
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "build_journal.py").write_text(
            "import os\nos.makedirs('journal', exist_ok=True)\nopen('journal/index.html','w').write('x')\n"
            "os.makedirs('scripts/__pycache__', exist_ok=True)\nopen('scripts/__pycache__/a.pyc','w').write('x')\n")
        (self.repo / "scripts" / "check.sh").write_text("#!/bin/bash\nexit 0\n")
        (self.repo / "sitemap.xml").write_text("base\n")
        (self.repo / ".gitignore").write_text("__pycache__/\n*.pyc\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")
        git(self.repo, "push", "-q", "origin", "main")
        self.queue = root / "queue"
        folder = self.queue / "01-hello"
        folder.mkdir(parents=True)
        for lang in publish_next.journal_md.LANGS:
            (folder / f"{lang}.md").write_text(SAMPLE.replace("lang: en", f"lang: {lang}"), encoding="utf-8")
        self._old = publish_next.REPO
        publish_next.REPO = str(self.repo)
        self.addCleanup(setattr, publish_next, "REPO", self._old)
        self._env = os.environ.pop("TODAYDATE_PUSH", None)
        self.addCleanup(lambda: os.environ.__setitem__("TODAYDATE_PUSH", self._env) if self._env else None)

    def run_publish(self, **kw):
        return publish_next.publish(str(self.queue), "2026-11-21", "14:30", **kw)

    def clean(self):
        return git(self.repo, "status", "--porcelain")

    def test_publish_commits_only_journal_files_and_moves_queue_without_push(self):
        before = git(self.origin, "rev-parse", "main")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertEqual(self.run_publish(pull=False), 0)
        self.assertIn("STOCK_ALERT: 발행 후 예약 원고 0편", stderr.getvalue())
        self.assertEqual(git(self.repo, "rev-list", "--count", "origin/main..HEAD"), "1")
        self.assertEqual(git(self.origin, "rev-parse", "main"), before)  # push 꺼짐
        files = git(self.repo, "show", "--name-only", "--format=", "HEAD").split("\n")
        self.assertIn("content/journal/hello/en.md", files)
        self.assertFalse([f for f in files if "pyc" in f or "__pycache__" in f])
        self.assertTrue((self.queue / ".published" / "01-hello").is_dir())
        self.assertFalse((self.queue / "01-hello").exists())

    def test_publish_skips_unreviewed_and_missing_editions_then_publishes_next(self):
        missing = self.queue / "02-missing"
        missing.mkdir()
        draft = self.queue / "01-draft"
        draft.mkdir()
        for source in (self.queue / "01-hello").glob("*.md"):
            text = source.read_text(encoding="utf-8")
            if source.name == "vi.md":
                text = text.replace("copy_review: iris\n", "")
            (draft / source.name).write_text(text, encoding="utf-8")
        (self.queue / "01-hello").rename(self.queue / "03-hello")

        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(self.run_publish(pull=False), 0)
        self.assertRegex(err.getvalue(), r"01-draft[^\n]*\bvi\b[^\n]*Iris")
        self.assertRegex(err.getvalue(), r"02-missing[^\n]*en\.md")
        self.assertEqual(err.getvalue().count("01-draft"), 1)
        self.assertEqual(err.getvalue().count("02-missing"), 1)
        self.assertTrue(draft.is_dir())
        self.assertTrue(missing.is_dir())
        self.assertTrue((self.queue / ".published/03-hello").is_dir())
        self.assertIn("content/journal/hello/en.md", git(self.repo, "show", "--name-only", "--format=", "HEAD"))
        self.assertFalse((self.repo / "content/journal/draft").exists())
        self.assertFalse((self.repo / "content/journal/missing").exists())
        self.assertEqual(self.clean(), "")

    def test_dirty_tree_exits_4(self):
        (self.repo / "stray.txt").write_text("x")
        self.assertEqual(self.run_publish(pull=False), 4)
        self.assertTrue((self.queue / "01-hello").is_dir())

    def test_not_main_exits_4(self):
        git(self.repo, "checkout", "-q", "-b", "other")
        self.assertEqual(self.run_publish(pull=False), 4)

    def test_dry_run_commits_nothing_and_keeps_queue(self):
        self.assertEqual(self.run_publish(pull=False, dry_run=True), 0)
        self.assertEqual(git(self.repo, "rev-list", "--count", "origin/main..HEAD"), "0")
        self.assertEqual(self.clean(), "")
        self.assertTrue((self.queue / "01-hello").is_dir())

    def test_build_failure_reverts(self):
        (self.repo / "scripts" / "build_journal.py").write_text("import sys\nsys.exit(1)\n")
        git(self.repo, "commit", "-qam", "break build")
        self.assertEqual(self.run_publish(pull=False), 5)
        self.assertEqual(self.clean(), "")
        self.assertFalse((self.repo / "content" / "journal" / "hello").exists())
        self.assertTrue((self.queue / "01-hello").is_dir())

    def test_no_ready_editions_finishes_without_running_git(self):
        (self.queue / "01-hello" / "ko.md").write_bytes(b"\xff\xfe\x00bad")  # UnicodeDecodeError
        err = io.StringIO()
        with patch.object(publish_next, "sh") as sh, patch.object(publish_next, "pull_rebase") as pull:
            with redirect_stderr(err):
                self.assertEqual(self.run_publish(), 3)
            sh.assert_not_called()
            pull.assert_not_called()
        self.assertIn("01-hello: 발행 준비 미완료", err.getvalue())
        self.assertIn("STOCK_ALERT", err.getvalue())
        self.assertEqual(self.clean(), "")
        self.assertFalse((self.repo / "content" / "journal" / "hello").exists())
        self.assertTrue((self.queue / "01-hello").is_dir())

    def test_child_stderr_reaches_publisher_log_on_success_and_failure(self):
        (self.repo / "scripts" / "build_journal.py").write_text(
            "import sys\nprint('build warning', file=sys.stderr)\n", encoding="utf-8")
        (self.repo / "scripts" / "check.sh").write_text(
            "#!/bin/bash\necho 'check failure' >&2\nexit 1\n", encoding="utf-8")
        git(self.repo, "commit", "-qam", "emit diagnostics")
        result = subprocess.run(
            [sys.executable, str(ROOT / "ops/publish_next.py"), "--queue", str(self.queue),
             "--date", "2026-11-21", "--time", "14:30", "--no-pull"],
            env={**os.environ, "TODAYDATE_REPO": str(self.repo)}, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 5)
        self.assertIn("build warning", result.stderr)
        self.assertEqual(result.stderr.count("check failure"), 1)
        self.assertEqual(self.clean(), "")

    def test_pull_conflict_aborts_rebase_and_leaves_clean_clone(self):
        other = Path(self.tmp.name) / "other"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "checkout", "-q", "-B", "main")
        (other / "sitemap.xml").write_text("remote\n")
        git(other, "commit", "-qam", "remote change")
        git(other, "push", "-q", "origin", "main")
        (self.repo / "sitemap.xml").write_text("local\n")
        git(self.repo, "commit", "-qam", "local change")
        self.assertEqual(self.run_publish(pull=True), 5)
        self.assertFalse((self.repo / ".git" / "rebase-merge").exists())
        self.assertFalse((self.repo / ".git" / "rebase-apply").exists())
        self.assertEqual(git(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertEqual(self.clean(), "")
        self.assertEqual((self.repo / "sitemap.xml").read_text(), "local\n")
        self.assertTrue((self.queue / "01-hello").is_dir())

    def test_pull_helper_sets_timeout_and_no_prompt(self):
        seen = {}
        real = subprocess.run

        def fake(cmd, **kw):
            if cmd[:2] == ["git", "pull"]:
                seen.update(kw)
                raise subprocess.TimeoutExpired(cmd, kw["timeout"])
            return real(cmd, **kw)
        subprocess.run, orig = fake, subprocess.run
        try:
            self.assertFalse(publish_next.pull_rebase())
        finally:
            subprocess.run = orig
        self.assertEqual(seen["timeout"], publish_next.PULL_TIMEOUT)
        self.assertEqual(seen["env"]["GIT_TERMINAL_PROMPT"], "0")


if __name__ == "__main__":
    unittest.main()
