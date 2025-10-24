# Seamless 스택 템플릿

이 런북은 `operations/seamless/` 에 있는 템플릿을 사용해 Seamless 배포를 부트스트랩하는 방법을 설명합니다.

## 디렉터리 개요

리포지토리는 다음 아티팩트를 제공합니다.

- `operations/seamless/docker-compose.seamless.yml` – Seamless 백필 코디네이터, QuestDB, Redis, MinIO를 기동하는 Compose 번들
- `qmtl/examples/seamless/presets.yaml` – QMTL SDK 기본값과 정렬된 SLA/컨포먼스 프리셋. 리포지토리 체크아웃에서 작업하는 운영자를 위해 `operations/seamless/presets.yaml` 사본도 제공합니다.
- `operations/seamless/README.md` – 서비스 및 구성 옵션 상세 문서
- `operations/config/*.yml` – 개발, 스테이징, 프로덕션 배포를 위한 QMTL 런타임 샘플 구성

Compose 번들은 합리적인 기본값을 포함하므로 스택을 시작하기 전에 `.env` 를 준비할 필요가 없습니다.

## 스택 실행

리포지토리 루트에서 다음 명령을 실행하세요.

```bash
docker compose -f operations/seamless/docker-compose.seamless.yml up -d
```

서비스를 검증하려면:

- 코디네이터 헬스 프로브 – `curl http://localhost:8080/healthz`
- QuestDB UI – `http://localhost:9000`
- MinIO 콘솔 – `http://localhost:9001`

`operations/config/*.yml` 을 수정해 코디네이터 주소를 지정하고 원하는 SLA/컨포먼스 프리셋을 선택하며 아티팩트 캡처를 설정하세요. 이 YAML 파일은 기존 `.env` 워크플로를 대체하며, CLI의 `--config` 플래그로 전달하거나 배포 도구에 마운트할 수 있습니다.

## 프리셋 사용

`seamless.presets_file` 을 원하는 문서로 지정하고 `seamless.sla_preset`, `seamless.conformance_preset` 을 선택하면 SLA와 컨포먼스 프리셋을 불러올 수 있습니다. `sla_presets` 항목은 `qmtl.runtime.sdk.sla.SLAPolicy` 에 대응하며, `conformance_presets` 항목은 경고 발생 시 Seamless가 응답을 차단할지 여부를 정의합니다. 기본 조합은 다음과 같습니다.

- `baseline` – SLA 위반 시 빠르게 실패하도록 엄격한 데드라인을 적용합니다.
- `strict-blocking` – 컨포먼스 경고가 발생하면 응답을 차단하고 1분 인터벌을 강제합니다.

탐색적 작업이나 부분 체결을 허용하는 백필 마이그레이션에는 `tolerant-partial`, `permissive-dev` 프리셋이 유용합니다.
