---
title: "릴리스 프로세스"
tags:
  - operations
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# 릴리스 프로세스

1. `CHANGELOG.md` 를 최신 릴리스 노트로 업데이트하고 관련 문서도 함께 수정합니다.
2. `python scripts/release_docs.py archive-docs --version <version>` 명령으로 이전 버전 문서를 보관합니다.
3. 보관된 버전과 지원 상태를 `docs/archive/README.md` 에 기록합니다.
4. `python scripts/release_docs.py sync-changelog` 로 문서 변경 로그를 재생성합니다.

{{ nav_links() }}
