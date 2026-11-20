#!/usr/bin/env python3
"""큐(~/.ipe/queue/todaydate/NN-slug/{en,ko}.md)의 가장 앞 글 하나를 발행한다.

순서: git pull --rebase → 가장 앞 글을 content/journal/<slug>/ 로 복사하며 date·time 을 지금으로 찍기
→ build_journal.py → scripts/check.sh (초록이어야 함) → git commit → (TODAYDATE_PUSH=1 일 때만) push
→ 큐 폴더를 .published/ 로 옮기기.

push 가 실패해도 발행은 성공으로 본다(커밋은 클론에 남아 다음 성공 push 때 같이 올라간다).
옵션: --dry-run 은 복사·빌드·검사까지만 하고 커밋·push·큐 이동을 하지 않으며, 만든 파일은 되돌린다.
     --no-pull 은 pull --rebase 를 건너뛴다(오프라인 시험용).
환경: TODAYDATE_REPO (기본 ~/Developer/datepick-rest) · TODAYDATE_PUSH=1 (기본 꺼짐)
종료 코드: 0 발행(또는 dry-run 통과) · 3 큐 비었음(STOCK_ALERT) · 4 main 아님/작업 트리 더러움 · 5 빌드·검사·커밋 실패.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.environ.get("TODAYDATE_REPO") or os.path.expanduser("~/Developer/datepick-rest"))
LANGS = ("en", "ko")
PUSH_TIMEOUT = 60  # 초. 네트워크가 멎어도 틱이 멈추지 않게 한다.
PULL_TIMEOUT = 60
# 발행이 만드는 경로만 add 한다(git add -A 금지).
ADD_PATHS = ("content/journal", "journal", "ko/journal", "sitemap.xml")


def next_folder(queue):
    names = sorted(n for n in os.listdir(queue)
                   if re.match(r"\d+-", n) and os.path.isdir(os.path.join(queue, n)))
    return names[0] if names else None


def stamp(text, date, hhmm):
    """front matter 의 date·time 을 찍는다(title 줄 바로 뒤)."""
    head, sep, rest = text.partition("\n---\n")
    out = []
    for line in head.split("\n"):
        if line.startswith(("date:", "time:")):
            continue
        out.append(line)
        if line.startswith("title:"):
            out += [f"date: {date}", f'time: "{hhmm}"']
    return "\n".join(out) + sep + rest


def editions(folder):
    """발행할 언어판 [(lang, text)] — en·ko 둘 다 있어야 한다."""
    out = []
    for lang in LANGS:
        path = os.path.join(folder, lang + ".md")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{folder}: {lang}.md 가 없다")
        with open(path, encoding="utf-8") as f:
            out.append((lang, f.read()))
    return out


def sh(*cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd or REPO, check=True, text=True, capture_output=True).stdout.strip()


def pull_rebase():
    """git pull --rebase. 실패·시간 초과면 rebase 를 중단해 클론을 깨끗하게 남기고 False."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=REPO, check=True, text=True,
                       capture_output=True, timeout=PULL_TIMEOUT, env=env)
        return True
    except subprocess.CalledProcessError as e:
        print(f"pull --rebase 실패: {(e.stderr or e.stdout or '').strip()}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print(f"pull --rebase 시간 초과({PULL_TIMEOUT}초)", file=sys.stderr)
    except OSError as e:
        print(f"git 을 실행하지 못함: {e}", file=sys.stderr)
    subprocess.run(["git", "rebase", "--abort"], cwd=REPO, capture_output=True, text=True, env=env)
    return False


def push():
    """origin main 으로 push. 실패·시간 초과는 stderr 에 남기고 False — 발행 자체는 실패로 보지 않는다."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        subprocess.run(["git", "push", "origin", "main"], cwd=REPO, check=True, text=True,
                       capture_output=True, timeout=PUSH_TIMEOUT, env=env)
        return True
    except subprocess.CalledProcessError as e:
        print(f"push 실패(발행은 유지, 커밋은 클론에 남음): {(e.stderr or e.stdout or '').strip()}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print(f"push 시간 초과({PUSH_TIMEOUT}초, 발행은 유지, 커밋은 클론에 남음)", file=sys.stderr)
    except OSError as e:
        print(f"push 를 실행하지 못함(발행은 유지): {e}", file=sys.stderr)
    return False


def _revert(created, dst):
    """이번에 만든 발행 흔적을 되돌린다 — 작업 트리는 pull 직후의 깨끗한 상태로."""
    sh("git", "reset", "--hard", "HEAD")
    sh("git", "clean", "-fd", "--", "content/journal", "journal", "ko/journal")
    if created and os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)


def publish(queue, date, hhmm, dry_run=False, pull=True):
    name = next_folder(queue)
    if not name:
        print("STOCK_ALERT: todaydate 저널 큐가 비었다", file=sys.stderr)
        return 3
    if sh("git", "rev-parse", "--abbrev-ref", "HEAD") != "main" or sh("git", "status", "--porcelain"):
        print("main 브랜치가 아니거나 작업 트리가 깨끗하지 않아 발행하지 않는다", file=sys.stderr)
        return 4
    if pull:
        if not pull_rebase():
            print("pull 실패로 발행하지 않는다(클론은 되돌림)", file=sys.stderr)
            return 5
    slug = name.split("-", 1)[1]
    dst = os.path.join(REPO, "content", "journal", slug)
    created = not os.path.isdir(dst)
    committed = False
    try:
        os.makedirs(dst, exist_ok=True)
        for lang, text in editions(os.path.join(queue, name)):
            with open(os.path.join(dst, lang + ".md"), "w", encoding="utf-8") as f:
                f.write(stamp(text, date, hhmm))
        sh("python3", "scripts/build_journal.py")
        sh("bash", "scripts/check.sh")
        if dry_run:
            print(f"dry-run ok: {slug} would publish as {date} {hhmm} KST (not committed)")
            _revert(created, dst)
            return 0
        sh("git", "add", "--", *[p for p in ADD_PATHS if os.path.exists(os.path.join(REPO, p))])
        sh("git", "commit", "-m", f"저널: {slug} ({date} {hhmm} KST)")
        committed = True
    except Exception as e:  # 예상 밖 예외(UnicodeDecodeError·OSError 등)에서도 되돌린다
        print((getattr(e, "stdout", "") or "") + (getattr(e, "stderr", "") or "") + repr(e), file=sys.stderr)
        if not committed:
            try:
                _revert(created, dst)
            except Exception as e2:
                print(f"되돌림 실패: {e2!r}", file=sys.stderr)
        return 5
    if os.environ.get("TODAYDATE_PUSH") == "1":
        push()  # 실패해도 발행은 성공 — 아래에서 큐를 옮긴다.
    done = os.path.join(queue, ".published")
    os.makedirs(done, exist_ok=True)
    shutil.move(os.path.join(queue, name), os.path.join(done, name))
    print(f"published {slug} {date} {hhmm} KST")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--time", required=True)
    ap.add_argument("--queue", required=True)
    ap.add_argument("--dry-run", action="store_true", help="복사·빌드·검사까지만; 커밋·push·큐 이동 없음")
    ap.add_argument("--no-pull", action="store_true", help="pull --rebase 를 건너뛴다")
    a = ap.parse_args(argv)
    return publish(a.queue, a.date, a.time, dry_run=a.dry_run, pull=not a.no_pull)


if __name__ == "__main__":
    sys.exit(main())
