# Seamless 스택 템플릿

이 런북은 `operations/` 하위 템플릿을 사용해 Seamless 배포를 부트스트랩하는 방법을 설명합니다.

## 디렉터리 개요

리포지토리는 다음 아티팩트를 제공합니다.

- `operations/docker-compose.full.yml` – Gateway/DAG Manager/WorldService/Seamless 코디네이터와 Redis/QuestDB/Postgres/Neo4j/Redpanda/MinIO를 포함한 풀스택 Compose 번들
- `operations/docker-compose.dev.override.yml` – 풀스택 번들을 로컬/인메모리 우선 설정으로 덮어쓰는 개발용 오버라이드
- `operations/seamless/docker-compose.seamless.yml` – Seamless 코디네이터 단독 번들(부분 스택/샘플 용도, 유지)
- `operations/config/dev.full.yml`, `operations/config/prod.full.yml` – 풀스택 번들에 바로 마운트할 수 있는 dev/prod 샘플 구성
- Helm(예정): Kubernetes 배포가 필요할 때 풀스택 Compose 구조를 그대로 반영하는 차트를 제공할 예정입니다.
- `qmtl/examples/seamless/presets.yaml` – QMTL SDK 기본값과 정렬된 SLA/컨포먼스 프리셋. 리포지토리 체크아웃에서 작업하는 운영자를 위해 `operations/seamless/presets.yaml` 사본도 제공합니다.
- `operations/seamless/README.md` – 서비스 및 구성 옵션 상세 문서
- `operations/config/*.yml` – 개발, 스테이징, 프로덕션 배포를 위한 QMTL 런타임 샘플 구성

Compose 번들은 합리적인 기본값을 포함하므로 스택을 시작하기 전에 `.env` 를 준비할 필요가 없습니다.

## 스택 실행

### 풀스택 (prod 기본)

```bash
docker compose -f operations/docker-compose.full.yml up -d
```

Prod 수준 설정은 `operations/config/prod.full.yml` 을 마운트하는 것을 권장합니다(필수 비밀/엔드포인트를 채워 넣으세요).

### 로컬/개발 오버라이드

```bash
docker compose -f operations/docker-compose.full.yml -f operations/docker-compose.dev.override.yml up -d
```

이 경로는 dev용 인메모리/로컬 설정과 `operations/config/dev.full.yml` 을 사용합니다. 코디네이터를 비워도 부팅하지만 prod에서는 `seamless.coordinator_url` 및 Redis/QuestDB/MinIO가 필수입니다.

### 업그레이드 노트

- 기존 `operations/seamless/docker-compose.seamless.yml` 사용자라면 prod/stage에서는 풀스택 번들로 전환해 코디네이터 스텁 폴백을 방지하세요.
- 단독 번들은 부분 스택/데모 용도로만 유지하고, prod에서는 `docker-compose.full.yml` + `operations/config/prod.full.yml`을 마운트해 사용하세요.
- Helm 전환은 로드맵에 있으며, 차트가 공개되기 전까지는 풀스택 Compose 번들을 사용하세요.

### 단독 코디네이터 샘플(부분 스택)

기존 단독 번들은 샘플/부분 스택 용도로 유지됩니다.

```bash
docker compose -f operations/seamless/docker-compose.seamless.yml up -d
```

서비스 검증:

- 코디네이터 헬스 프로브 – `curl http://localhost:8080/healthz`
- QuestDB UI – `http://localhost:9000`
- MinIO 콘솔 – `http://localhost:9001`

`operations/config/*.yml` 을 수정해 코디네이터 주소를 지정하고 원하는 SLA/컨포먼스 프리셋을 선택하며 아티팩트 캡처를 설정하세요. 이 YAML 파일은 기존 `.env` 워크플로를 대체하며, CLI의 `--config` 플래그로 전달하거나 배포 도구에 마운트할 수 있습니다.

## 프리셋 사용

`seamless.presets_file` 을 원하는 문서로 지정하고 `seamless.sla_preset`, `seamless.conformance_preset` 을 선택하면 SLA와 컨포먼스 프리셋을 불러올 수 있습니다. `sla_presets` 항목은 `qmtl.runtime.sdk.sla.SLAPolicy` 에 대응하며, `conformance_presets` 항목은 경고 발생 시 Seamless가 응답을 차단할지 여부를 정의합니다. 기본 조합은 다음과 같습니다.

- `baseline` – SLA 위반 시 빠르게 실패하도록 엄격한 데드라인을 적용합니다.
- `strict-blocking` – 컨포먼스 경고가 발생하면 응답을 차단하고 1분 인터벌을 강제합니다.

탐색적 작업이나 부분 체결을 허용하는 백필 마이그레이션에는 `tolerant-partial`, `permissive-dev` 프리셋이 유용합니다.
