# Seamless 풀스택 번들 설계 (분산 백필 1급 서비스화)

## 배경 및 목표
- 현재 Seamless 분산 백필 코디네이터는 별도 Compose 번들에서만 기동되고, `coordinator_url`이 비어 있으면 SDK가 인메모리 스텁으로 자동 폴백한다. 반면 Gateway/DAG Manager/WorldService는 dev→인메모리, prod→외부 리소스 필수라는 일관된 규칙을 따른다.
- 목적: 분산 백필 코디네이터를 Gateway/DAG Manager/WorldService와 같은 1급 운영 서비스로 격상시키고, prod용 풀스택 번들(Compose/Helm)에서 함께 배포되도록 표준화한다. dev는 안전한 스텁/로컬 번들을 유지하되 prod에서의 폴백 누락을 방지한다.

## 범위
- 서비스 위상 재정렬: 분산 백필 코디네이터를 코어 서비스로 포함할지, ControlBus를 1급 서비스로 노출할지 결정.
- 환경별 동작 규칙: dev/prod 프로필에 따른 기본값, 검증, 폴백 정책 정의.
- 배포 자산: prod 전체 Compose/Helm 번들 설계( Gateway, DAG Manager, WorldService, Coordinator, ControlBus, Redis/QuestDB/Neo4j/Kafka/Postgres/MinIO 등 필수 의존성 포함). 기존 `operations/seamless/docker-compose.seamless.yml`는 dev/부분 스택용 보존하며, 안내 문서는 [Seamless Stack Templates](../operations/seamless_stack.md)를 참조한다.
- 비범위: 코디네이터 내부 프로토콜 변경, SLA/컨포먼스 스키마 변경.

## 설계 안

### 1. 서비스 위상 및 ControlBus
- 분산 백필 코디네이터: Gateway/DAG Manager/WorldService와 동일한 “코어 데이터/제출 경로” 서비스로 취급한다.
- ControlBus: 기본 구현을 Redpanda로 고정한다(개발은 단일 노드, 프로드는 3노드 오버레이). gw/dagmanager/ws 공통 의존성이며, dev에서는 ControlBus 미사용 모드나 로컬 Redis-only 모드도 허용된다.
- 의존 리소스: 코디네이터가 요구하는 Redis(락/레이트리미터), QuestDB(커버리지/백필 메타), MinIO/S3(아티팩트), HTTP 포트는 풀스택 번들에서 기본 제공한다.

### 2. 환경별 동작 규칙
- dev 프로필:
  - 기본: `coordinator_url` 미지정 시 인메모리 스텁 유지. 경고 로그로 “prod에서는 URL 필수” 안내.
  - 선택: `docker-compose.dev.override.yml` 수준에서 코디네이터+필수 리소스만 올리는 경량 옵션 제공.
- prod 프로필:
  - `seamless.coordinator_url` 미설정 시 `qmtl config validate --target all`에서 오류 처리(폴백 금지).
  - 런타임 부팅 시 코디네이터 헬스 체크는 제한된 재시도(예: 총 3회, ~30초 내) 후 실패 시 프로세스를 종료하고 스텁 전환은 허용하지 않는다.
  - `operations/config/prod.full.yml`에 코디네이터/QuestDB/Redis/MinIO/ControlBus/Kafka/Neo4j/Postgres DSN이 모두 채워진 상태를 기본값으로 제공.

### 3. 배포 번들 구조 (prod 기본)
- 단일 Compose/Helm 번들에 다음을 포함:
  - `gateway`, `dagmanager`, `worldservice` (기존 런타임)
  - `seamless-coordinator` (HTTP 8080/metrics, Redis/QuestDB/MinIO 의존)
  - `controlbus` (Kafka/Redpanda + Zookeeper 또는 단일 Redpanda) — gw/dagmanager/ws 공통
  - `redis` (세션/락/레이트리미터), `postgres`(gateway DB), `neo4j`(dagmanager), `questdb`(데이터), `minio`(아티팩트)
- dev 오버라이드: gw/dagmanager/ws를 인메모리/로컬 모드로 두고, 코디네이터 없이도 부팅 가능하게 `-f docker-compose.full.yml -f docker-compose.dev.override.yml` 구성 제공.
- 기존 `operations/seamless/docker-compose.seamless.yml`는 샘플/부분 스택 용도로 보존하되, prod 기본 경로는 풀스택 번들로 안내한다.

### 4. 설정·검증 변경
- `config validate`에 Seamless 섹션 검사 추가:
  - prod 프로필: `coordinator_url` 누락, Redis/QuestDB/MinIO DSN 누락, 코디네이터 헬스 체크 실패 시 오류.
  - dev 프로필: `coordinator_url` 누락 시 경고만 출력.
- 런타임 초기화 시 코디네이터 생성 실패 → 스텁 폴백을 금지하고 예외/로그 후 종료(프로필 기반).
- 샘플 설정: `operations/config/prod.full.yml`, `operations/config/dev.full.yml`를 추가하고 문서에서 `--config`로 사용 예시 제공.

### 5. 마이그레이션 단계
1) 문서: 본 설계를 반영해 Seamless/Operations 가이드에 prod 기본 경로를 풀스택 번들로 명시.  
2) 설정 템플릿: `operations/config`에 dev/prod full 템플릿 추가, 코디네이터 URL/DSN 채워진 상태로 배포.  
3) 검증 훅: `config validate`에 Seamless 검사 추가, prod 프로필에서 폴백 금지.  
4) Compose/Helm: `operations/docker-compose.full.yml`(또는 helm chart) 신설, 기존 Seamless 단독 번들은 샘플로 유지.  
5) 런타임 수위: `_create_default_coordinator`에 프로필 기반 스텁 금지 옵션 도입(prod).  
6) 점진 배포: staging에서 풀스택 번들로 검증 후 prod 롤아웃, 기존 단독 코디네이터 사용자에게는 설정 갱신 가이드 제공.

### 6. 구현 체크리스트(TODO)
- 설정 템플릿: `operations/config/dev.full.yml`(로컬 기본값, 코디네이터 선택)과 `operations/config/prod.full.yml`(모든 DSN 채움, 코디네이터 필수) 추가.
- 검증: `qmtl config validate --target all`에 Seamless 검사 추가, prod에서 `coordinator_url`/Redis/QuestDB/MinIO 미가용 시 오류, dev는 경고.
- 런타임 가드: `_create_default_coordinator`에 프로필 기반 스텁 금지 + 제한 재시도 헬스 체크 적용.
- 번들: `operations/docker-compose.full.yml` + `docker-compose.dev.override.yml` 추가, Helm chart에도 동일 구조 반영.
- 문서: `operations/seamless_stack.md`, `operations/docker.md`, Seamless 가이드에서 prod 기본 번들을 이 경로로 안내하고, 기존 단독 코디네이터 사용자용 업그레이드 노트를 추가.

### 7. 참조 값 및 헬스 체크
- 코디네이터: `http://seamless-coordinator:8080`, 헬스 `/healthz`, 재시도 3회(약 10초 백오프, 총 ~30초) 후 실패 시 종료.
- Redis(락/레이트리미트): `redis://redis:6379/3`, 키 프리픽스 `seamless:*`.
- QuestDB: `postgresql://questdb:8812/qmtl`, 테이블 프리픽스 `seamless_*`.
- MinIO: `http://minio:9000`, 버킷 `qmtl-seamless`, 프리픽스 `artifacts/`.
- ControlBus(Redpanda): 브로커 `redpanda:9092`, 토픽 프리픽스 `qmtl.controlbus.*`.

### 6. 공유 의존성 격리 방안
- Redis: 서비스별 DB 인덱스 또는 키 프리픽스(`seamless:*`, `gateway:*`, `dagmanager:*`)를 강제하고, 코디네이터 락/레이트리미트 키를 다른 캐시와 분리한다. prod에서는 노이즈 영향이 예상되면 코디네이터 전용 논리 DB나 클러스터를 권장한다.
- Kafka/ControlBus: 토픽 프리픽스(`qmtl.controlbus.*`)와 ACL을 적용해 공유 버스와의 충돌을 막는다.
- MinIO/S3: Seamless 아티팩트와 기타 워크로드를 버킷 또는 프리픽스로 분리하고, IAM 정책을 분리한다.
- QuestDB: 코디네이터가 쓰는 커버리지/메타 테이블은 고정 프리픽스나 별도 DB로 격리해 전략 데이터와 충돌하지 않게 한다.
- 네트워크/리소스: prod에서는 내부 네트워크 세그먼트에 배치하고 서비스별 리소스 제한(Compose/Helm limits/requests)으로 다른 모듈로 인한 자원 고갈을 방지한다.

### 8. 매니지드 의존성
- QuestDB/MinIO를 매니지드로 쓸 경우 URL/크리덴셜 오버라이드 스니펫을 문서화하고, 번들에서는 오버라이드로 제외할 수 있게 한다.
- ControlBus는 기본 포함(Redpanda)으로 유지하되, 외부 Kafka 사용 시 토픽 프리픽스/ACL/헬스 프로브를 명시한다.
- 공유 인프라를 쓸 때는 버킷/프리픽스, DB 사용자/IAM을 서비스별로 분리해 권한을 최소화한다.

### 9. 오픈 포인트
- QuestDB/MinIO를 외부 매니지드로 둘 경우 번들에서 제외할지 여부: 기본은 포함, 매니지드 사용 시 오버라이드 문서화.
