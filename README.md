# datepick-rest

「오늘 어때」(가칭 datepick) 웹 랜딩·디자인 에셋. 문서는 _ipe/foundry/F-031_datepick/.

사이트 일관성 점검(sitemap·hreflang·내부 링크, 표준 라이브러리만): `python3 tests/check_site.py`

## 저널

원고는 `content/journal/<slug>/<BCP47 태그>.md`에 둡니다. 새 글은 표준 언어 12개의 원고와 각 파일의 `copy_review: iris`, `copy_review_date: YYYY-MM-DD`가 있어야 빌드에 들어갑니다. 기존 글은 현재 주소와 언어판을 유지합니다.

예약 발행은 macOS launchd의 `rest.ipe.todaydate-publish`가 담당합니다. 검수된 다음 원고는 `~/.ipe/queue/todaydate/NN-<slug>/`에 넣습니다. 큐가 비면 `~/.ipe/logs/todaydate-publish.log`에 `STOCK_ALERT`가 남습니다.

`python3 scripts/build_journal.py`로 정적 파일을 생성하고 `bash scripts/check.sh`로 확인합니다. 비공개 웹킷은 로컬에서 `python3 scripts/kit_lock.py sync --kit <웹킷 클론 경로>`로 복사하며 이 레포에는 잠금 파일만 기록합니다.
