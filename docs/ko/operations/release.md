---
title: "릴리스 프로세스"
tags:
  - operations
author: "QMTL Team"
last_modified: 2026-01-10
---

{{ nav_links() }}

# 릴리스 프로세스

1. `CHANGELOG.md` 를 최신 릴리스 노트로 업데이트하고 관련 문서도 함께 수정합니다.
2. `archive-docs` 명령은 `docs/ko` 와 `docs/en` 만 아카이브 대상으로 삼습니다.
   기본 동작은 **복사(copy)** 이며, 결과는 `docs/archive/<version>/{ko,en}/` 에 저장됩니다.
3. 안전 모드로 아카이브 대상과 경로를 먼저 확인하려면 `--dry-run` 을 실행합니다.
4. 실제 보관은 다음 명령으로 수행합니다.
5. 보관된 버전과 지원 상태를 별도 아카이브 로그(배포 문서 외부)에 기록합니다.
6. `python scripts/release_docs.py sync-changelog` 로 `docs/ko/reference/CHANGELOG.md` 와
   `docs/en/reference/CHANGELOG.md` 를 재생성합니다.

## archive-docs 실행 예시

```bash
# 안전 확인 (파일 변경 없음)
python scripts/release_docs.py archive-docs --version 1.2.3 --dry-run

# 기본 복사 모드 (docs/archive/1.2.3/ko, docs/archive/1.2.3/en 생성)
python scripts/release_docs.py archive-docs --version 1.2.3 --status supported

# 필요할 때만 이동 모드 (파괴적)
python scripts/release_docs.py archive-docs --version 1.2.3 --mode move
```

{{ nav_links() }}
