---
title: "릴리스 프로세스"
tags:
  - operations
author: "QMTL Team"
last_modified: 2026-01-11
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
7. 릴리스 컷 체크리스트를 따라 태그/릴리스/산출물/검증 링크를 정리합니다.

## archive-docs 실행 예시

```bash
# 안전 확인 (파일 변경 없음)
python scripts/release_docs.py archive-docs --version 1.2.3 --dry-run

# 기본 복사 모드 (docs/archive/1.2.3/ko, docs/archive/1.2.3/en 생성)
python scripts/release_docs.py archive-docs --version 1.2.3 --status supported

# 필요할 때만 이동 모드 (파괴적)
python scripts/release_docs.py archive-docs --version 1.2.3 --mode move
```

## Release 0.1 릴리스 컷 체크리스트

다음 항목을 모두 기록해 두어야 Release 0.1 컷이 완료됩니다. 릴리스 노트에는 아래 결과 링크를 반드시 포함합니다.

### 1) 태그 생성

```bash
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

### 2) GitHub Release 생성

- 태그 `v0.1.0` 기준으로 GitHub Release를 생성합니다.
- 릴리스 노트에 `CHANGELOG.md` 요약과 함께 DoD 검증 결과 링크를 남깁니다.
  - 예: CI run URL, 실행 로그/아티팩트 위치 링크

### 3) 산출물 빌드 및 첨부

- Wheel: `uv pip wheel .` 또는 `uv build --wheel`
- sdist: `python -m build`
- 생성 경로: 기본적으로 `dist/` 디렉터리에 `.whl`, `.tar.gz` 가 생성됩니다.
- GitHub Release에 `dist/` 산출물을 첨부합니다.

### 4) DoD 검증 기록

- [Release 0.1 완료 기준(DoD)](release_0_1_definition_of_done.md) 문서의 검증 명령을 실행합니다.
- 실행 결과 링크(예: CI run 또는 로그 저장 위치)를 릴리스 노트에 남깁니다.

{{ nav_links() }}
