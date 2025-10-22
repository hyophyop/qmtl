# 문서 국제화 가이드

본 프로젝트는 MkDocs Material과 `mkdocs-static-i18n` 플러그인을 사용해 다국어 문서를 제공합니다.

- 기본 로케일: `en`
- 추가 로케일: `ko`
- 디렉터리 구조: `docs/<locale>/...` (예: `docs/en/guides/...`)

## 번역 추가 또는 업데이트

1) 대상 로케일 폴더에 파일을 추가합니다.

- 영어 경로를 그대로 미러링합니다. 예: `docs/en/guides/foo.md` → `docs/ko/guides/foo.md`.
- 제목 구조를 동일하게 유지하고 상대 링크를 사용합니다.

2) 내비게이션 제목을 업데이트합니다(선택).

- MkDocs 내비게이션에 노출되는 페이지라면 현지화된 제목이 있는지 확인합니다.
- 새로운 내비 항목을 추가할 때는 `mkdocs.yml`의 `nav_translations`(ko 설정 아래)에 항목을 등록합니다.

3) 문서 빌드를 검증합니다.

- 로컬에서 전체 빌드를 실행합니다.
  - `uv run mkdocs build`
- 두 로케일을 모두 검증하며 누락되거나 잘못된 링크를 조기에 발견할 수 있습니다.

4) 메시지 카탈로그(클라이언트 문자열)를 관리합니다.

- 개발 의존성 설치: `uv pip install -e .[dev]`
- 메시지 추출: `uv run pybabel extract -F babel.cfg -o qmtl/locale/qmtl.pot .`
- 한국어 초기화/업데이트:
  - 최초 실행: `uv run pybabel init -l ko -i qmtl/locale/qmtl.pot -d qmtl/locale`
  - 이후 업데이트: `uv run pybabel update -l ko -i qmtl/locale/qmtl.pot -d qmtl/locale`
- 카탈로그 컴파일: `uv run pybabel compile -d qmtl/locale`

## 링크 검사 정책

정적 링크 검사기는 진행 중인 번역에서 발생하는 오탐을 피하기 위해 기본 로케일만 검사합니다.

- `mkdocs.yml`의 i18n 구성을 읽어 비기본 로케일은 건너뜁니다.
- 보관(archive)된 문서도 제외됩니다.

로컬 실행:

- `python scripts/check_docs_links.py`

## CLI 언어 재정의

CLI는 사용자 메시지용 언어 힌트를 지원합니다.

- 전역 옵션: `--lang {en,ko}` (예: `qmtl --lang ko project --help`)
- 환경 변수: `QMTL_LANG=ko`

재정의가 없으면 CLI는 일반적인 로케일 환경 변수를 탐색한 뒤 영어를 기본값으로 사용합니다.
