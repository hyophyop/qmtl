---
title: "전략 개발 및 테스트 워크플로"
tags: []
author: "QMTL Team"
last_modified: 2025-09-22
---

{{ nav_links() }}

# 전략 개발 및 테스트 워크플로

> **실무 개발 가이드 및 체크리스트**
>
> - **관심사 분리(SoC)**: 각 모듈은 단일 책임 원칙을 지키고, 인터페이스로 의존성을 최소화하세요. (자세한 내용은 [architecture.md](../architecture/architecture.md) 참고)
> - **테스트 독립성**: 테스트는 서로 의존하지 않게 작성하고, 실패 시 원인을 쉽게 파악할 수 있도록 명확한 assert와 메시지를 사용하세요.
> - **코딩 규칙**: 전략/노드 구현 시 모듈화, 함수 분리, 주석 및 docstring 작성 등 기본 원칙을 지켜주세요.
> - **트러블슈팅**: 설치/실행/연결 오류 발생 시 [docs/reference/faq.md](../reference/faq.md)와 아래 '자주 발생하는 문제'를 참고하세요.
> - **운영/배포**: 배포 전 테스트, 설정 백업, 롤백 플랜, 모니터링 설정을 반드시 확인하세요. (자세한 내용은 [docs/operations/monitoring.md](../operations/monitoring.md), [docs/operations/canary_rollout.md](../operations/canary_rollout.md) 참고)
> - **폴더/파일 역할 요약**:
>   - `strategy.py`: 전략 진입점, Strategy 클래스 구현
>   - `qmtl.yml`: 환경 및 서비스 연결 설정
>   - `generators/`, `indicators/`, `transforms/`: 사용자 확장 노드 구현
>   - `tests/`: 단위/통합 테스트 코드

---

이 가이드는 새로운 QMTL 전략을 생성하고 검증하는 전형적인 단계를 안내합니다.
SDK 설치와 프로젝트 초기화에서 시작하여 테스트 스위트 실행으로 마무리합니다.

## 0. QMTL 설치

가상 환경을 만들고 편집 모드로 패키지를 설치합니다. 자세한 내용은
[문서 홈](../index.md)을 참고하세요. 기본 단계는 다음과 같습니다:

```bash
uv venv
uv pip install -e .[dev]
```

## 1. 프로젝트 초기화

전략을 위한 디렉터리를 만들고 스캐폴드를 생성합니다. 사용 가능한 템플릿을 조회한 후,
선택한 템플릿과 선택적 샘플 데이터를 사용해 프로젝트를 초기화합니다:

```bash
qmtl project init --list-templates
qmtl project init --path my_qmtl_project --strategy branching --with-sample-data
cd my_qmtl_project
```

이 명령은 예제 `strategy.py`, `qmtl.yml` 구성 파일, 그리고 `generators`, `indicators`,
`transforms` 빈 패키지를 복사합니다. 이 폴더들을 통해 커스텀 노드를 추가하여 SDK를 확장할 수 있습니다.


## 2. 스캐폴드 살펴보기

- `strategy.py` – SDK를 사용하는 최소 예제 전략
- `qmtl.yml` – Gateway와 DAG Manager용 샘플 구성
- `generators/`, `indicators/`, `transforms/` – 추가 노드를 구현하는 확장 패키지

> **구조 설명:** 각 폴더/파일의 역할은 위 '실무 개발 가이드' 참고.

기본 전략을 실행해 정상 동작을 확인합니다. 외부 서비스가 구성되지 않은 경우 오프라인 모드가 사용됩니다:

```bash
python strategy.py
```
스캐폴드 스크립트는 기본적으로 `Runner.offline()`을 사용하므로 외부 서비스가 필요하지 않습니다.
환경에 연결하려면 `Runner.run(world_id=..., gateway_url=...)`를 호출하도록 스크립트를 수정하세요.
이 모드는 WorldService의 결정과 활성화 이벤트를 따릅니다.

Gateway는 WorldService를 프록시하며, SDK는 `/events/subscribe`가 반환하는 토큰화된 WebSocket을 통해 제어 이벤트를 수신합니다. 활성화 및 큐 업데이트는 Gateway 상태를 직접 읽지 않고 이 불투명(opaque) 제어 스트림으로 전달됩니다.

## 2a. 실행 예시 출력

다음 스니펫은 깨끗한 컨테이너에서 위 명령을 실행한 결과를 보여줍니다. 스캐폴드를 생성한 뒤 디렉터리 구조는 다음과 같습니다:

```text
$ ls -R my_qmtl_project | head
my_qmtl_project:
generators
indicators
qmtl.yml
strategy.py
transforms
...
```

Gateway/WorldService에 도달할 수 없는 상태에서 `Runner.run(...)`을 호출하면,
제어 연결이 복구될 때까지 전략은 안전한 compute‑only 상태(주문 게이트 OFF)를 유지합니다.

> **자주 발생하는 문제**
> - Gateway URL 미지정: `--gateway-url` 인자 추가 또는 `Runner.offline()` 사용
> - 의존성 충돌: `uv pip install -e .[dev]`로 재설치 권장

## 3. 전략 개발

`strategy.py`를 수정하거나 확장 패키지 내에 새 모듈을 만듭니다. 각 전략은 `Strategy`를 상속하고
`setup()` 메서드에서 `Node` 인스턴스를 연결합니다. 유용한 기본 클래스에는 `StreamInput`,
`TagQueryNode`, `ProcessingNode` 등이 있습니다. 이 개념에 대한 전체 소개는
[sdk_tutorial.md](sdk_tutorial.md)를 참고하세요.

접속 문자열 같은 구성 옵션은 `qmtl.yml`에 있습니다. 로컬 개발에 적합하며, 필요하면 프로덕션 서비스로
지정하도록 조정할 수 있습니다.

> **개발 가이드라인**
> - 각 노드는 단일 책임 원칙을 지키고, 인터페이스로만 상호작용하세요.
> - 복잡한 로직은 별도 함수/클래스로 분리하고, 주석과 docstring을 작성하세요.
> - 변경 시 반드시 관련 문서와 테스트를 함께 수정하세요.

## 4. 월드와 함께 실행

의존성 없이 로컬 테스트를 할 때는 `Runner.offline()`을 사용하세요. 통합 실행의 경우
`Runner.run(strategy_cls, world_id=..., gateway_url=...)`로 전환합니다. 활성화와 큐 업데이트는
Gateway의 `/events/subscribe` WebSocket 제어 스트림으로 전달되며, 정책과 활성화의 권한은 WS에 있습니다.

실행 도메인은 이제 봉투(envelope)에 명시적으로 표기됩니다:

- WorldService 결정은 `effective_mode`(`validate|compute-only|paper|live`)를 방출합니다.
- Gateway/SDK는 규범 매핑(`validate → backtest(주문 게이트 OFF)`, `compute-only → backtest`, `paper → dryrun`, `live → live`)을 사용해 `execution_domain`(`backtest|dryrun|live|shadow`)을 도출합니다.
- 예시: [`dryrun_live_switch_strategy.py`]({{ code_url('qmtl/examples/strategies/dryrun_live_switch_strategy.py') }})는 `connectors.execution_domain`을 읽어 `dryrun`과 `live`를 전환합니다. 레거시 `trade_mode=paper` 값은 호환성 유지를 위해 `dryrun`으로 변환됩니다.
- 오프라인 실행은 `backtest` 도메인을 반영하므로, `validate` 결정은 프로모션 완료 전까지 주문을 발행하지 않습니다.

```bash
# start with built-in defaults
qmtl service gateway
qmtl service dagmanager server

# or load a custom configuration
qmtl service gateway --config qmtl/examples/qmtl.yml
qmtl service dagmanager server --config qmtl/examples/qmtl.yml
```

별도 프로세스를 실행하거나 `parallel_strategies_example.py` 스크립트를 사용하면 여러 전략을 병렬로 실행할 수 있습니다.

> **팁:** 운영 환경에서는 `qmtl.yml` 설정을 반드시 백업하고, 롤백 플랜을 준비하세요.

## 5. Test Your Implementation

Always run the unit tests in parallel before committing code:

```bash
uv run -m pytest -W error -n auto
```

컨테이너 내부에서의 샘플 실행은 다음과 같이 성공적으로 종료되었습니다:

```text
======================= 260 passed, 1 skipped in 47.15s ========================
```

E2E(종단 간) 테스트에는 Docker가 필요합니다. 스택을 시작하고 테스트를 실행하세요:

```bash
docker compose -f tests/docker-compose.e2e.yml up -d
uv run -m pytest -n auto tests/e2e
```

테스트 환경에 대한 자세한 내용은 [docs/operations/e2e_testing.md](../operations/e2e_testing.md)를 참고하세요.
원한다면 휠 빌드를 테스트와 병렬로 실행할 수 있습니다:

```bash
# Example of running wheels and tests in parallel
uv pip wheel . &
uv run -m pytest -W error -n auto
wait

### 테스트 종료 및 정리(Teardown)

테스트에서 백그라운드 서비스를 시작하는 경우(예: TagQueryManager 구독 또는 ActivationManager),
모든 리소스를 정리하기 위해 세션 컨텍스트 매니저 사용을 권장합니다:

```python
async with Runner.session(MyStrategy, world_id="w", gateway_url="http://gw") as strategy:
    ...  # assertions
```

동기 테스트 등으로 ``async with``를 사용할 수 없을 때는 다음 보조 함수를 사용하세요:

```python
strategy = Runner.run(MyStrategy, world_id="w", gateway_url="http://gw")
try:
    ...  # assertions
finally:
    Runner.shutdown(strategy)
```

이 보조 함수들은 멱등하며, 백그라운드 서비스가 활성화되어 있지 않아도 안전합니다.

### 테스트 모드 시간 예산

`qmtl.yml`에서 `test.test_mode`를 활성화하면 불안정한 환경에서의 hang 가능성을 줄이기 위한 보수적 클라이언트 측 시간 예산이 적용됩니다:

- HTTP 클라이언트: 짧은 폴링 주기 및 명시적 상태 확인
- WebSocket 클라이언트: 더 짧은 수신 타임아웃과 전체 최대 실행 시간(≈5초)

```yaml
test:
  test_mode: true
```
```

> **테스트 작성 가이드**
> - 테스트는 독립적으로 작성하고, 다른 테스트에 의존하지 않게 하세요.
> - 실패 시 원인을 쉽게 파악할 수 있도록 assert 메시지를 명확히 작성하세요.
> - 커버리지 기준을 정하고, 주요 로직은 반드시 테스트를 작성하세요.
> - 통합 테스트와 단위 테스트를 구분해 관리하세요.

## 6. 다음 단계

Consult [architecture.md](../architecture/architecture.md) for a deep dive into the overall
framework and `qmtl/examples/` for reference strategies. When ready, deploy the
Gateway and DAG Manager using your customized `qmtl.yml`.

> **운영/배포 체크리스트**
> - 테스트 통과 및 커버리지 확인
> - 설정 파일 백업 및 버전 관리
> - 모니터링/알림 설정 ([docs/operations/monitoring.md](../operations/monitoring.md))
> - 점진적 배포/롤백 플랜 ([docs/operations/canary_rollout.md](../operations/canary_rollout.md))
> - 배포 후 주요 로그/지표 확인

> **참고자료**
> - [architecture.md](../architecture/architecture.md): 전체 시스템 구조
> - [sdk_tutorial.md](sdk_tutorial.md): SDK 및 전략 개발 예제
> - [faq.md](../reference/faq.md): 자주 묻는 질문
> - [monitoring.md](../operations/monitoring.md): 모니터링 및 운영
> - [canary_rollout.md](../operations/canary_rollout.md): 점진적 배포 전략
> - [qmtl/examples/]({{ code_url('qmtl/examples/') }}): 다양한 전략 예제

{{ nav_links() }}
