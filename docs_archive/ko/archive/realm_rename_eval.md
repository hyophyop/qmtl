---
title: "Realm 용어 평가"
tags: [world, realm, terminology]
author: "QMTL Team"
last_modified: 2025-08-21
---

# Realm 용어 평가 _(보관)_

> **상태(2025-11):** 참고용 보관 문서입니다. **World**에서 **Realm**으로의 용어
> 변경은 채택되지 않았으며, 문서·구성·API·운영 도구 전체에서 **World**가 공식
> 용어로 유지됩니다.

이 문서는 QMTL 전반에서 **World** 용어를 **Realm**으로 교체하는 제안을 검토합니다.

## 도메인 적합성(Domain Fit)

현재 "World"는 연관된 전략과 정책을 묶는 최상위 포트폴리오 경계를 의미합니다. "Realm"은 자율적 도메인을 의미한다는 점에서 유사하며, 지리/시장적 뉘앙스가 과도하게 얽히지 않아 더 깔끔합니다. 영어/한국어(“렐름”) 모두 자연스럽고, 서드파티 도구에서 흔한 "world" 명칭과의 혼동도 줄일 수 있습니다.

## 영향 범위(Impact Scope)

용어 변경은 문서, 구성 경로, API, 툴링에 모두 영향을 줍니다. 대략적인 검색으로 아키텍처/운영/레퍼런스 문서에서 "World" 참조가 100건 이상 확인됩니다. 핵심 대상은 `docs/ko/world/*.md`, `docs/ko/architecture/worldservice.md`, World API 레퍼런스, 활성화 런북 등입니다. 코드 샘플과 구성 스니펫 또한 `config/worlds/<id>.yml`, `qmtl world` CLI 동사를 전제로 작성되어 있습니다.

## 프로토타입: config/realms

- 정책 파일 경로를 `config/worlds/`에서 `config/realms/<realm_id>.yml`로 변경합니다.
- Gateway와 Runner는 world 정의에 의존하지 않고 realm 파일을 직접 로드합니다.
- 문서 예제는 새 경로만 사용합니다.

## 프로토타입: `qmtl realm` CLI

- 기존 서브커맨드를 그대로 반영합니다: `qmtl realm create`, `qmtl realm list`, `qmtl realm policy add` 등.
- 전환 기간 동안 `qmtl world` 사용 시 폐기(deprecation) 경고를 출력하고 새 구현으로 포워딩합니다.
- 마이그레이션 완료 전까지 도움말과 `--help` 출력에서 두 용어를 병기합니다.

## 미해결 질문

- 데이터베이스 테이블과 이벤트 타입(예: `WorldUpdated`)도 이름을 바꾸거나 별칭을 둘까요?
- `world` 제거 전 이중 용어 병기는 얼마나 유지해야 할까요?
- 일부 통합이 `world` 문자열 자체에 의존해, 별칭만으로는 깨질 가능성이 있나요?

프로젝트 전역 개명에 앞서 추가 논의가 필요합니다.
