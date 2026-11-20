#!/bin/bash
# Green gate for the todaydate journal — run before every commit. Exit 0 = green.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== 1/3 unit tests"; python3 -m unittest discover -s tests -q
echo "== 2/3 journal build is up to date"; python3 scripts/build_journal.py --check
echo "== 3/3 static site checks"; python3 tests/check_site.py
echo "GREEN"
