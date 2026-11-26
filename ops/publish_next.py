#!/usr/bin/env python3
"""큐(~/.ipe/queue/todaydate/NN-slug/<lang>.md)에서 발행 준비가 끝난 첫 글을 발행한다.

순서: 큐 검수 확인 → git pull --rebase → 선택한 글을 content/journal/<slug>/ 로 복사하며 date·time 을 지금으로 찍기
→ build_journal.py → scripts/check.sh (초록이어야 함) → git commit → (TODAYDATE_PUSH=1 일 때만) push
→ 큐 폴더를 .published/ 로 옮기기.

push 가 실패해도 발행은 성공으로 본다(커밋은 클론에 남아 다음 성공 push 때 같이 올라간다).
옵션: --dry-run 은 복사·빌드·검사까지만 하고 커밋·push·큐 이동을 하지 않으며, 만든 파일은 되돌린다.
     --no-pull 은 pull --rebase 를 건너뛴다(오프라인 시험용).
     --check-queue 는 큐의 12개 언어판과 검수 상태를 읽기 전용으로 확인한다.
환경: TODAYDATE_REPO (기본 ~/Developer/datepick-rest) · TODAYDATE_PUSH=1 (기본 꺼짐)
종료 코드: 0 발행(또는 dry-run 통과) · 3 준비된 원고 없음(STOCK_ALERT) · 4 main 아님/작업 트리 더러움 · 5 빌드·검사·커밋 실패.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.environ.get("TODAYDATE_REPO") or os.path.expanduser("~/Developer/datepick-rest"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import journal_md
PUSH_TIMEOUT = 60  # 초. 네트워크가 멎어도 틱이 멈추지 않게 한다.
PULL_TIMEOUT = 60
# 발행이 만드는 경로만 add 한다(git add -A 금지).
JOURNAL_PATHS = ("journal", *(f"{lang.lower()}/journal" for lang in journal_md.LANGS if lang != "en"))
ADD_PATHS = ("content/journal", *JOURNAL_PATHS, "sitemap.xml")


def queue_folders(queue):
    return sorted((name for name in os.listdir(queue)
                   if re.fullmatch(r"[0-9]+-[a-z0-9]+(?:-[a-z0-9]+)*", name)
                   and os.path.isdir(os.path.join(queue, name))),
                  key=lambda name: (int(name.split("-", 1)[0]), name))


def next_folder(queue):
    names = queue_folders(queue)
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
    """발행할 언어판 [(lang, text)] — 12개 언어판과 Iris 검수가 있어야 한다."""
    out = []
    for lang in journal_md.LANGS:
        path = os.path.join(folder, lang + ".md")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{lang}.md 가 없다")
        with open(path, encoding="utf-8") as f:
            out.append((lang, f.read()))
    journal_md.validate_editions({lang: journal_md.parse(text) for lang, text in out})
    return out


def check_queue(queue):
    """발행 전에 원고별 언어판과 검수 상태를 확인한다. 파일은 건드리지 않는다."""
    names = queue_folders(queue)
    if not names:
        print("STOCK_ALERT: todaydate 저널 큐가 비었다", file=sys.stderr)
        return 3
    invalid = False
    for name in names:
        try:
            editions(os.path.join(queue, name))
        except (OSError, ValueError) as exc:
            invalid = True
            print(f"{name}: 발행 준비 미완료 — {exc}", file=sys.stderr)
        else:
            print(f"{name}: 언어판 {len(journal_md.LANGS)}개와 검수 표기 확인")
    if len(names) <= 1:
        print(f"STOCK_ALERT: 예약 원고 {len(names)}편 — 다음 발행분 보충 필요", file=sys.stderr)
    return 5 if invalid else 0


def sh(*cmd, cwd=None):
    result = subprocess.run(cmd, cwd=cwd or REPO, check=True, text=True, capture_output=True)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.stdout.strip()


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
    sh("git", "clean", "-fd", "--", "content/journal", *JOURNAL_PATHS)
    if created and os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)


def publish(queue, date, hhmm, dry_run=False, pull=True):
    names = queue_folders(queue)
    if not names:
        print("STOCK_ALERT: todaydate 저널 큐가 비었다", file=sys.stderr)
        return 3
    for name in names:
        try:
            ready_editions = editions(os.path.join(queue, name))
        except (OSError, ValueError) as exc:
            print(f"STOCK_ALERT: {name}: 발행 준비 미완료 — {exc}", file=sys.stderr)
        else:
            break
    else:
        print("STOCK_ALERT: todaydate 저널 큐에 발행 준비가 끝난 원고가 없다", file=sys.stderr)
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
        for lang, text in ready_editions:
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
    remaining = len(queue_folders(queue))
    if remaining <= 1:
        print(f"STOCK_ALERT: 발행 후 예약 원고 {remaining}편 — 큐 보충 필요", file=sys.stderr)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date")
    ap.add_argument("--time")
    ap.add_argument("--queue", required=True)
    ap.add_argument("--check-queue", action="store_true", help="원고와 검수 상태만 확인")
    ap.add_argument("--dry-run", action="store_true", help="복사·빌드·검사까지만; 커밋·push·큐 이동 없음")
    ap.add_argument("--no-pull", action="store_true", help="pull --rebase 를 건너뛴다")
    a = ap.parse_args(argv)
    if a.check_queue:
        return check_queue(a.queue)
    if not a.date or not a.time:
        ap.error("--date와 --time이 필요합니다")
    return publish(a.queue, a.date, a.time, dry_run=a.dry_run, pull=not a.no_pull)


if __name__ == "__main__":
    sys.exit(main())
