# SDK 레이어 가이드

## 0. 목적과 Core Loop 상 위치

- 목적: SDK 내부 의존성 흐름을 정리해 불필요한 import 순환을 막고 인터페이스를 얇게 유지하기 위한 기준을 설명합니다.
- Core Loop 상 위치: Core Loop 각 단계(전략 제출, 히스토리 warm‑up, 평가, 활성화)가 **예측 가능한 SDK 레이어 구조** 위에서 동작하도록 보조하는 유지보수/설계 가이드입니다(주 독자는 SDK 유지보수자).

이 문서는 SDK 내부 의존성 흐름을 정리해 불필요한 import 순환을 막고 인터페이스를 얇게 유지하기 위한 기준을 설명합니다.

- 선호하는 방향: `foundation → protocols → core → nodes → io → strategies`
- 프로토콜: `StreamLike`, `NodeLike`, `HistoryProvider*`, `EventRecorder`처럼 공유 인터페이스는 `qmtl.runtime.sdk.protocols`에 두고 구체적인 노드 클래스를 직접 참조하지 않습니다.
- 코어(cache, backfill, data_io)는 노드 구현을 import하지 말고 공유 프로토콜만 사용합니다.
- 노드는 코어에 의존할 수 있지만, 코어가 노드로 역참조하여 순환이 생기지 않도록 합니다.

## 검증

- import 순환: `uv run --with grimp python scripts/check_import_cycles.py --baseline scripts/import_cycles_baseline.json`
- 레이어 가드(core/io/seamless → nodes): `uv run --with grimp python scripts/check_sdk_layers.py`
