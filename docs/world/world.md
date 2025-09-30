# QMTL 월드(World) — 전략 생애주기 관리 사양 v1

본 문서는 docs/world/world_todo.md와 docs/world/world_refined.md의 아이디어를 통합하여, “월드(World)”라는 알파 정제 단위를 QMTL에 무리 없이 도입하기 위한 단일 사양과 작업 명세를 제시한다. 목표는 기존 QMTL 구성요소(DAG Manager, Gateway, SDK Runner, Metrics)를 최대한 재사용하면서 정책 기반의 자동 평가·승격·강등을 제공하는 것이다. 불필요한 프레임워크 확장을 피하고, 단계적 도입이 가능하도록 설계를 최소화했다.

- 기준 문서: ./docs/architecture/architecture.md, ./docs/architecture/gateway.md, ./docs/architecture/dag-manager.md
- 저장소 경계: qmtl/에는 재사용 가능한 유틸/노드/게이트웨이 확장만 추가한다. 전략(알파) 구현은 루트 strategies/ 폴더에 둔다.

## 1. 목적과 비범위

- 목적
  - 월드(World)를 전략 상위 추상화로 두고, 정책(WorldPolicy)에 따라 전략을 평가·선정하고 실행 모드를 관리한다.
  - 데이터 통화성(Data Currency), 표본 충분성, 성과 임계값, 상관/리스크 제약, 히스테리시스를 조합해 자동 승격/강등 결정을 내린다.
  - Runner는 단일 진입점(월드 주도 실행)으로 동작하며, Gateway API, DAG Manager, SDK 메트릭을 그대로 활용한다.
- 비범위(초기 단계)
  - 별도 분산 스케줄러, 신규 메시지 브로커, 신규 그래프 모델 추가는 하지 않는다.
  - 전략 코드 자동 배포/프로세스 관리(런너 생성/종료)는 별도 운영 도구로 유지하고, 본 문서는 “선정/전환 계획 생성 + 활성화 게이트”에 집중한다.

## 2. 핵심 개념 및 데이터

- World: 전략 묶음의 실행 경계를 나타내는 상위 단위. 예: `world_id = "crypto_mom_1h"`.
- WorldPolicy(vN): 월드별 평가·선정 정책의 버전드 스냅샷. YAML로 관리하며 파서/검증기를 통해 로드.
- StrategyInstance: 동일 전략 코드라도 파라미터/사이드/월드별 인스턴스로 관리된다.
- Activation Table: 월드별 활성 전략 목록과 사이드·가중치 등 실행 플래그를 저장하는 경량 캐시(Redis Hash 권장).
- Audit Log: 평가 입력 스냅샷, 결정 결과(Top‑K/승격/강등), 적용 내역(2‑Phase) 기록. 데이터베이스는 Gateway에서 이미 사용하는 백엔드(Postgres/SQLite/Memory)를 재사용한다.

권장 저장 위치
- 정책 정의 파일: `config/worlds/<world_id>.yml`
- 활성 테이블: Redis 키 `world:<world_id>:active`
- 감사 로그/정책 버전: Gateway Database(기존 백엔드) 테이블 확장

## 3. 상태·전환(최소 사양)

- 전략 실행은 월드(WorldService)의 결정에 따르며, Runner는 모드를 선택하지 않는다. 전환은 2‑Phase 원자성으로 계획한다.
- 월드 관점 상태: `evaluating`(평가 중) / `applying`(계획 적용 중) / `steady`(안정)만 추적(운영용). 복잡한 월드 FSM은 도입하지 않는다.
- 2‑Phase 전환(요지)
  1) Freeze/Drain: 주문 차단(게이트 ON) 후 대기; 필요 시 포지션 청산/이월 규칙 적용
  2) Switch: 활성 테이블 교체(Top‑K), Runner 게이트 상태 반영
  3) Unfreeze: 주문 허용(게이트 OFF)
  - 모든 단계는 idempotent run_id로 추적하고 실패 시 롤백 포인트를 남긴다.

노드/태그/큐 상태 등 세부 실행 상태는 DAG Manager/SDK의 정의를 그대로 따른다. (참고: ./docs/architecture/dag-manager.md)

## 4. 평가 정책 DSL(간결형)

YAML 기반으로 “게이트(Gates) → 점수(Score) → 제약(Constraints) → Top‑K → 히스테리시스(Hysteresis)”의 5단 구성을 최소 표현으로 제공한다.

```yaml
# config/worlds/crypto_mom_1h.yml
world: crypto_mom_1h
version: 1

data_currency:
  max_lag: 5m        # now - data_end <= 5분이면 validate, 아니면 catch-up 동안 compute-only
  min_history: 60d   # 최소 과거 기간 충족 전 지표는 참고용만
  bar_alignment: exchange_calendar

selection:
  gates:
    and:
      - sample_days >= 30
      - trades_60d >= 40
      - sharpe_mid >= 0.60
      - max_dd_120d <= 0.25
  score: "sharpe_mid + 0.1*winrate_long - 0.2*ulcer_mid"
  topk:
    total: 8
    by_side: { long: 5, short: 3 }
  constraints:
    correlation:
      max_pairwise: 0.8
    exposure:
      gross_budget: { long: 0.60, short: 0.40 }
      max_leverage: 3.0
      sector_cap: { per_sector: 0.30 }
  hysteresis:
    promote_after: 2     # 2회 연속 통과
    demote_after: 2
    min_dwell: 3h        # 최소 체류 시간

position_policy:
  on_promote: flat_then_enable   # 기본: 포지션 미이월
  on_demote: disable_then_flat
```

게이트 표현은 단순한 AND/OR 합성과 비교 연산으로 제한한다. 점수는 제한된 수식(화이트리스트 함수·변수)만 허용한다. 제약은 쌍상관, 익스포저 상한 등 전형 규칙부터 시작한다.

## 5. 결정 알고리즘(요지)

데이터 통화성 → 게이트 → 점수 → 제약 → Top‑K → 히스테리시스 순으로 결정한다. 아래는 의사 코드 요약이다.

```python
def decide_initial_mode(now, data_end, max_lag):
    return "active" if (now - data_end) <= max_lag else "validate"

def gate_metrics(m, policy):
    if m.sample_days < policy.min_sample_days: return "insufficient"
    if m.trades_60d < policy.min_trades: return "insufficient"
    return "pass" if eval_expr(policy.gates, m) else "fail"

def apply_hysteresis(prev, checks, h):
    dwell_ok = time_in_state(prev) >= h.min_dwell
    if checks.consecutive_pass >= h.promote_after and dwell_ok: return "PROMOTE"
    if checks.consecutive_fail >= h.demote_after and dwell_ok: return "DEMOTE"
    return "HOLD"
```

지표 소스
- 성능 지표(Sharpe, MDD 등)는 전략이 노드로 산출하거나 SDK 메트릭(qmtl/runtime/sdk/metrics.py)을 연계해 Prometheus에서 수집한다.
- 표본 수·체결 수 등은 이벤트 레코더/리포지토리(예: QuestDB)에서 조회한다.

## 6. 통합 지점(기존 기능 재사용)

- Runner: 월드 결정(WS)에 따르는 단일 진입점 `run(world_id=...)`과 `offline()`만 제공한다. 월드 결정 결과는 “활성화 게이트”를 통해 주문 발동을 제어한다.
- Gateway: 제출/상태/큐 조회 API 그대로 사용(../architecture/gateway.md). 월드용 얇은 엔드포인트(활성 테이블 조회/적용, 감사 기록)만 확장한다.
- DAG Manager: NodeID/토픽, TagQuery 동작은 변경하지 않는다(../architecture/dag-manager.md).
- 메트릭: SDK/Gateway/DAG Manager의 기존 Prometheus 메트릭을 재사용한다.

### 6.1 World‑First Runner Execution

월드 정책이 “실행 모드”를 결정하도록 Runner 실행을 일원화한다.

- CLI
  - `qmtl tools sdk run --world-id <id> --gateway-url <url>`: 월드‑우선 실행.
  - `qmtl tools sdk offline`: 게이트웨이 없이 로컬 실행.
- 실행 흐름(요지)
  1) Runner가 `--world`를 받으면 Gateway `GET /worlds/{id}/decide`를 호출해 `effective_mode`와 이유/파라미터를 얻는다.
  2) Runner는 별도 모드로 분기하지 않고, WS 결정에 따라 주문 게이트/검증만 제어한다.
  3) Gateway가 불가하면 `--world-file`로 동일 결정을 로컬 계산한다. 둘 다 없으면
     사용자가 지정한 로컬 폴백(`offline`)으로 전환한다.
- 주문 게이트 상호작용
  - 모드와 별개로, 주문은 `Activation Table`의 활성 여부가 `true`일 때만 발동한다.
  - `OrderGateNode`는 Gateway `GET /worlds/{id}/activation` 또는 WS 신호를 구독해 활성 변경을 반영한다.
- 즉시 라이브 세계관
  - “컷오프 제한이 없는” 샘플 월드를 제공(게이트 완화, 히스테리시스/표본 최소값 낮춤).
  - 그래도 `--allow-live` 플래그와 월드‑스코프 RBAC가 필요하다.

## 7. 주문 게이트(OrderGate) 설계(경량)

- 형태: SDK 공용 ProcessingNode(예: `OrderGateNode`)
- 동작: 실행 시점에 Gateway의 활성 테이블을 조회(HTTP/WS 캐시)해 “활성=false”면 주문 메시지를 차단하거나 0 크기로 축소한다.
- 이점: 전략 코드에 최소 침습으로 게이트를 삽입할 수 있고, 월드 전환을 안전하게 2‑Phase로 진행할 수 있다.
- 위치: 주문/브로커리지 노드 앞단에 한 개만 배치. 기본 정책은 보수적(차단 우선).

초기 최소 규격
- GET `/worlds/{world_id}/activation?strategy_id=...&side=...` → `{ active: true/false, weight: 0.0~1.0 }`
- WS `worlds.activate` 브로드캐스트(옵션): 활성 세트/가중치 변경 시 갱신

## 8. 운영/안전장치(필수)

- 데이터 통화성(최신성) 게이트: `now - data_end <= max_lag` 충족 전에는 compute-only로 실행(주문 게이트 OFF)
- 표본 충분성: 지표별 최소 일수/체결 수 충족 전 결과는 참고용
- 2‑Phase 전환: Freeze/Drain → Switch → Unfreeze, idempotent run_id
- 리스크 컷: 월드 총 드로우다운/VAR/레버리지 상한 위반 시 즉시 게이트 ON(서킷)
- 알림 규격: 승격/강등/적용 실패/지연/서킷 이벤트를 표준 알림으로 송신

권장 SLO 지표(예)
- `world_eval_duration_ms_p95`, `world_apply_duration_ms_p95`
- `world_activation_skew_seconds`(게이트 반영 지연)
- `promotion_fail_total`, `demotion_fail_total`

## 9. 멀티‑월드 & 자원

- 기본: World‑SILO(격리)로 시작한다. 추후 비용 절감을 위해 Shared 노드(공유 토픽) 도입은 선택.
- 공유 도입 시: NodeID 해시 스킴/네임스페이스로 경계 보장, Mark‑&‑Sweep는 Drain을 동반한다.

## 10. 단계적 도입 계획(작업 명세)

Phase 0 — 정책·지표 파이프 준비(무중단)
- [docs] 본 문서 추가 및 예시 정책 추가(`config/worlds/*.yml`)
- [sdk] 성과 지표 산출 노드 또는 기존 메트릭 노출 정리(샘플 전략 예제 업데이트)

Phase 1 — 평가 엔진(읽기 전용) + 활성 테이블
- [gateway] `worlds.py`: WorldPolicy 모델/파서/검증기(whitelist 수식), 감사 로그 스키마
- [gateway] API(읽기 전용): `GET /worlds/{id}/activation`(Redis 조회), `POST /worlds/{id}/evaluate`(dry‑run 평가→계획만 반환)
- [scripts] `scripts/world_eval.py`: 정책 로드→지표 스냅샷→결정→계획 출력(CLI)

Phase 2 — 2‑Phase 적용기 + 안전장치
- [gateway] 적용 API: `POST /worlds/{id}/apply`(Freeze/Drain→Switch→Unfreeze, run_id)
- [gateway] 리스크 컷·서킷 스위치(활성 테이블 즉시 OFF)
- [gateway] 알림/메트릭(승격/강등/실패/지연)

Phase 3 — SDK 주문 게이트(선택적)
- [sdk] `OrderGateNode` 추가: 경량 pass‑through/차단
- [examples] 게이트 삽입 예시 및 가이드 업데이트

Phase 4 — 멀티‑월드 최적화(선택적)
- [gateway] Shared 노드 네임스페이스/파티션 뷰, Mark‑&‑Sweep with Drain

각 Phase는 독립 배포 가능하며, 실패 시 롤백 범위를 최소화한다.

### 10.1 Runner/CLI 단계적 전환(월드‑우선)

- Phase R1 — 기능 추가(비파괴)
  - CLI: `qmtl tools sdk run --world-id <id> --gateway-url <url>`, `qmtl tools sdk offline`.
  - Runner: WS 결정에 따르는 단일 경로(`run`/`offline`)만 유지.
  - 문서/예제: 월드‑우선 실행 예제와 즉시‑라이브 월드 YAML 제공.

로컬 실행 예시
```bash
qmtl tools sdk run strategies.my:Alpha --world-id crypto_mom_1h --gateway-url http://localhost:8000
```

## 11. 경계·원칙(정책)

- 재사용 우선: Gateway API/DB, DAG Manager, SDK Runner/메트릭을 최대한 그대로 사용
- 단순성 우선: 월드 자체 FSM을 최소화하고, 핵심은 “평가→활성 테이블→게이트”로 축소
- 보수적 기본값: 히스테리시스/쿨다운/리스크 컷을 기본 켜진 상태로 제공
- 저장소 경계 준수: qmtl/에는 공용 기능만, 전략 코드는 strategies/에 유지

## 12. 부록 — 예시 API/스키마(요약)

자세한 스펙과 오류 의미, 인증 흐름은 World API Reference 문서를 참조:
- ../reference/api_world.md

결정(DecisionEnvelope)

```http
GET /worlds/{world}/decide?as_of=2025-08-28T09:00:00Z HTTP/1.1
→ {
  "world_id": "crypto_mom_1h",
  "policy_version": 3,
  "effective_mode": "validate",   # validate|active
  "reason": "data_currency_ok&gates_pass&hysteresis",
  "as_of": "2025-08-28T09:00:00Z",
  "ttl": "300s",                   # 캐시 유효 시간(권장)
  "etag": "w:crypto_mom_1h:v3:1724835600"
}
```

활성(ActivationEnvelope)

```http
GET /worlds/{world}/activation?strategy_id=abcd&side=long HTTP/1.1
→ {
  "world_id": "crypto_mom_1h",
  "strategy_id": "abcd",
  "side": "long",
  "active": true,
  "weight": 1.0,
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "run_id": "7a1b4c...",
  "ts": "2025-08-28T09:00:00Z"
}
```

평가 실행(계획만)

```http
POST /worlds/{world}/evaluate HTTP/1.1
{ "as_of": "2025-08-28T09:00:00Z" }
→ { "topk": [...], "promote": [...], "demote": [...], "notes": "..." }
```

적용(2‑Phase)

```http
POST /worlds/{world}/apply HTTP/1.1
{ "run_id": "...", "plan": { ... } }
→ { "ok": true, "run_id": "..." }
```

이벤트 구독(은닉 ControlBus 핸드오버)

```http
POST /events/subscribe HTTP/1.1
{ "world_id": "crypto_mom_1h", "strategy_id": "...", "topics": ["activation", "queues"] }
→ {
  "stream_url": "wss://gateway.example/ws/evt?ticket=...",  # Opaque; 내부적으로 ControlBus일 수 있음
  "token": "<jwt>",              # scope: world:*, strategy:*, topics
  "topics": ["activation"],      # 서버가 정규화한 구독 목록
  "expires_at": "2025-08-28T09:30:00Z",
  "fallback_url": "wss://gateway.example/ws"
}
```

---

본 사양은 기존 시스템과 충돌 없이 단계적으로 도입되며, 첫 적용 시에는 Phase 1까지로도 “정책 평가 + 활성 테이블(읽기 전용)”을 통해 운영 검증을 시작할 수 있다. 이후 게이트/2‑Phase를 순차 반영해 자동 전환의 안정성과 재현성을 확보한다.

## 13. 월드 레지스트리(CRUD & 전역 접근)

월드는 전략 제출과 독립적으로 생성/수정/삭제/조회가 가능해야 하며, 프레임워크 전역에서 동일한 ID로 접근 가능해야 한다. 중앙 진실 원천(SSOT)은 WorldService의 월드 레지스트리이며, Gateway는 외부 접근을 위한 프록시/캐시 역할을 수행한다. 내부 전파는 Redis 캐시와 ControlBus(은닉) 이벤트를 사용하고, 외부에는 Gateway WS/HTTP로 노출한다.

### 13.1 데이터 모델(경량)

- worlds (DB)
  - `world_id`(pk, slug), `name`, `description`, `owner`, `labels[]`,
    `created_at`, `updated_at`, `default_policy_version`, `state`(ACTIVE|SUSPENDED|DELETED),
    `allow_live`(bool, 기본 false), `circuit_breaker`(bool, 기본 false)
- world_policies (DB)
  - `(world_id, version)`(pk), `yaml`(text), `checksum`, `status`(DRAFT|ACTIVE|DEPRECATED),
    `created_by`, `created_at`, `valid_from`(옵션)
- world_activation (Redis)
  - 키: `world:<id>:active` → `{ strategy_id|side : {active, weight} }`
  - 스냅샷은 감사 로그에 주기 보관
- world_audit_log (DB)
  - `id`, `world_id`, `actor`, `event`(create/update/apply/evaluate/activate/override),
    `request`, `result`, `created_at`

설계 원칙: 정책 원문은 버전별로 DB에 보관하되, 장기 아카이브는 오브젝트 스토리지(S3 등)로 이관 가능. 삭제는 소프트 삭제(참조 안전성 확보).

### 13.2 API(REST, 초안)

- CRUD
  - `POST /worlds` → 세계 생성 `{id, name, description, policy_yaml, set_default?}`
  - `GET /worlds` → 목록 필터(소유자/라벨/상태)
  - `GET /worlds/{id}` → 메타 + 기본 정책 버전
  - `DELETE /worlds/{id}` → 소프트 삭제(활성 세트 존재 시 실패/강제 옵션)
  - `PUT /worlds/{id}` → 메타데이터 변경(name/desc/labels/allow_live)
- 정책 버전
  - `POST /worlds/{id}/policies` → 새 버전 업로드 `{version, policy_yaml, activate?}`
  - `GET /worlds/{id}/policies` / `GET /worlds/{id}/policies/{v}`
  - `POST /worlds/{id}/set-default?v=V` → 기본 정책 전환(감사 로그 남김)
- 결정/활성/평가
  - `GET /worlds/{id}/decide?as_of=...` → `{effective_mode, reason, params}`
  - `GET /worlds/{id}/activation?strategy_id=...&side=...` → `{active, weight}`
  - `PUT /worlds/{id}/activation` → 운영자 수동 오버라이드(선택, TTL 포함)
  - `POST /worlds/{id}/evaluate` → 정책 평가(계획만 반환)
  - `POST /worlds/{id}/apply` → 2‑Phase 적용(run_id)
  - `GET /worlds/{id}/audit` → 감사 이벤트 스트림

보안: 토큰 기반 world‑scope RBAC(creator/owner, readers, operators). 민감 엔드포인트(`apply`, `activation PUT`)는 별도 권한.

### 13.3 CLI(서브커맨드, 초안)

```
qmtl world create --id crypto_mom_1h --file config/worlds/crypto_mom_1h.yml --set-default
qmtl world show crypto_mom_1h
qmtl world list --owner alice --state ACTIVE
qmtl world policy add crypto_mom_1h --file policy_v2.yml --version 2 --activate
qmtl world policy set-default crypto_mom_1h 2
qmtl world decide crypto_mom_1h --as-of 2025-08-28T09:00:00Z
qmtl world eval crypto_mom_1h | jq .
qmtl world apply crypto_mom_1h --plan plan.json --run-id $(uuidgen)
qmtl world activation get crypto_mom_1h --strategy <sid> --side long
qmtl world activation set crypto_mom_1h --strategy <sid> --side long --active=false --ttl 3600 --reason maintenance
qmtl world delete crypto_mom_1h --force
```

오프라인 지원: `--world-file <yaml>`로 로컬 결정을 재현하고, `decide/eval`은 로컬 파서로 동작(네트워크/DB 미사용). Runner의 `--world-file`과 동일 포맷.

### 13.4 전역 접근 보장

- SSOT는 Gateway 레지스트리. 모든 서비스/런너는 REST/WS로 조회한다.
- 캐시: Redis(키 `world:*`), 변경 시 CloudEvent(`world.updated`) 브로드캐스트로 SDK/운영 툴 동기화.
- 일관성: 변경 API는 etag/resource_version을 요구(낙관적 잠금)해 경합 업데이트 방지.

### 13.5 운영 주의점

- 삭제: 활성 전략 세트가 존재하면 기본 거부; `--force` 시 Drain + 게이트 ON 이후에만 진행.
- 롤백: 정책 버전은 언제든 `set-default`로 롤백. `apply` 실패 시 활성 테이블은 이전 스냅샷으로 복원.
- 가시성: Grafana에 World 대시보드(정책 버전, 활성 세트, 서킷 상태, 최근 알림) 제공.

## 14. 이벤트 스트림(은닉 ControlBus) 핸드오버

SDK는 오직 Gateway와만 통신한다. ControlBus는 내부 제어 버스이며 외부에 명시적으로 드러나지 않는다. 실행 단계에서 Gateway가 “이벤트 스트림 기술서(EventStreamDescriptor)”를 반환하고, SDK는 이를 사용해 실시간 이벤트를 푸시로 수신한다.

- 역할 분리
  - SSOT: WorldService(세계/정책/활성), DAG Manager(그래프/큐)
  - 배포/팬아웃: ControlBus(내부), 외부에는 Gateway가 단일 접점
- EventStreamDescriptor(불투명)
  - `stream_url`(wss): 게이트웨이 도메인 하의 URL. 내부 구현상 ControlBus로 프록시/리다이렉트될 수 있으나 클라이언트는 불문에 부친다.
  - `token`(JWT): 구독 범위(world_id/strategy_id/topics)와 만료를 포함. SDK는 그대로 사용.
  - `topics`: 서버가 정규화한 구독 주제(예: `activation`, `queues`, `policy`).
  - `expires_at`: 재구독 시점 안내.
  - `fallback_url`: 주 스트림 불가 시 사용. 미제공 시 HTTP 폴링 경로를 사용.
- 이벤트 타입(요약)
  - ActivationUpdated: `{world_id, strategy_id, side, active, weight, etag, run_id, ts}`
  - QueueUpdated: `{tags[], interval, queues[], etag, ts}`
  - PolicyUpdated: `{world_id, version, checksum, status, ts}`
- 순서/중복
  - 키 단위(world_id, (tags, interval))로만 순서 보장. 중복 가능 → etag/run_id로 멱등 처리.
- 실패/대체 경로
  - 스트림 실패 시 Gateway WS `fallback_url` 또는 주기적 `GET /worlds/{id}/activation`/`/queues/by_tag`로 보정.
  - 만료 혹은 401/403 발생 시 `POST /events/subscribe`로 재발급.
- 보안/RBAC
  - Gateway가 토큰을 발급하고 WorldService 권한을 대행 검증. 민감 토픽은 world‑scope 권한 요구.
- SLO/관측(권장)
  - `event_subscribe_latency_ms_p95` ≤ 150ms, `event_fanout_lag_ms_p95` ≤ 200ms
  - 드롭/재연결/스큐 지표와 감사 로그(WorldService 원본 이벤트 ID 포함) 노출

실행 흐름(요지)
1) Runner 시작 → Gateway로 전략 제출/월드 결정 조회
2) Gateway → `POST /events/subscribe` 응답으로 EventStreamDescriptor 제공
3) SDK → `stream_url`에 연결, `token`으로 인증, `topics` 구독
4) 실시간 Activation/Queue 업데이트를 수신하여 `OrderGateNode` 및 TagQueryManager에 반영

## 15. 컴포넌트 관계(모듈/인터페이스 명세)

본 절은 sdk, gateway, controlbus(은닉), worldservice, dagmanager 간의 책임·경계·인터페이스를 모듈 관점에서 명시한다.

### 15.1 소유권(SSOT)과 책임

- WorldService(SSOT)
  - 월드/정책 CRUD, 버전 관리, 결정/평가/적용, 활성 테이블 관리, 감사/알림, RBAC
- DAG Manager(SSOT)
  - 그래프/노드/토픽/태그 쿼리, Diff, 버전/롤백, 큐 메타데이터
- Gateway(프록시/캐시)
  - SDK 외부 단일 접점; 전략 제출/상태/큐 조회 프록시, 월드 API 프록시, 이벤트 스트림 발급, 캐시/서킷/관측
- ControlBus(배포/팬아웃)
  - 제어 이벤트의 내부 퍼브/섭 허브(비공개). SSOT 아님. WS/DM의 업데이트를 다수 Gateway 인스턴스로 팬아웃
- SDK(클라이언트/런타임)
  - 전략 직렬화/제출, 태그 해석, OrderGateNode로 주문 게이트, 이벤트 스트림 구독/적용

### 15.2 인터페이스(요약)

- SDK → Gateway (HTTP)
  - `/strategies`(제출), `/strategies/{id}/status`, `/queues/by_tag`, `/worlds/*`(프록시), `/events/subscribe`
  - 인증: 사용자 토큰(JWT)
- Gateway → WorldService (HTTP/gRPC)
  - `/worlds` CRUD, `/worlds/{id}/decide|activation|evaluate|apply`, `/worlds/{id}/audit`
  - 인증: 서비스 간 토큰(mTLS/JWT), world‑scope RBAC 위임
- Gateway → DAG Manager (gRPC/HTTP)
  - `get_queues_by_tag`, Diff/콜백, 센티넬 트래픽 업데이트 수신
- WorldService → ControlBus (Publish)
  - `ActivationUpdated`, `PolicyUpdated`, `WorldUpdated`
- DAG Manager → ControlBus (Publish)
  - `QueueUpdated`
- Gateway → ControlBus (Subscribe)
  - WS/DM 이벤트를 수신 → SDK로 WS 재전송. 실패 시 HTTP 폴백

### 15.3 이벤트 타입(요약)

- ActivationUpdated: `{world_id, strategy_id, side, active, weight, etag, run_id, ts}`
- QueueUpdated: `{tags[], interval, queues[], etag, ts}`
- PolicyUpdated: `{world_id, version, checksum, status, ts}`

모든 이벤트는 키 단위(예: `world_id`, `(tags, interval)`)로만 순서를 보장하며, 멱등키(`etag`/`run_id`)로 중복 안전성을 확보한다.

### 15.4 지연/내결함성 예산(권장)

- SDK→Gateway 제출 p95 ≤ 150ms, 큐 조회 p95 ≤ 200ms
- 이벤트 팬아웃 지연 p95 ≤ 200ms, 최대 스큐(`activation_skew_seconds`) ≤ 2s
- Gateway 프록시 타임아웃: WS/DM 각각 독립 서킷 브레이커 적용(예: 300ms/500ms)
- 실패 기본값: 월드 결정을 못 받으면 compute-only(주문 게이트 OFF)로 폴백, 활성 미확인 시 게이트 OFF

### 15.5 개발 단위 매핑

- qmtl/runtime/sdk/
  - Runner: `run_async(world_id)`, `OrderGateNode`, TagQueryManager(WS/폴백)
- gateway/
  - api: `/worlds/*` 프록시, `/events/subscribe`, ControlBus 구독자, 캐시/서킷
- worldservice/
  - api: CRUD/Policy/Decide/Evaluate/Apply, 감사/알림, RBAC
- dagmanager/
  - api: get_queues_by_tag, Diff, 센티넬/토픽 관리
- controlbus/
  - control.* 토픽/채널 구성, 파티션 키, 보관/압축 정책, 관측

### 15.6 상호작용 개요(다이어그램)

```mermaid
graph LR
  subgraph Client
    SDK[SDK / Runner]
  end
  subgraph Edge
    GW[Gateway]
  end
  subgraph Core
    WS[WorldService (SSOT Worlds)]
    DM[DAG Manager (SSOT Graph)]
    CB[(ControlBus — internal)]
  end

  SDK -- HTTP submit/decide/activation --> GW
  GW -- proxy --> WS
  GW -- proxy --> DM
  WS -- publish --> CB
  DM -- publish --> CB
  GW -- subscribe --> CB
  GW -- WS (opaque) --> SDK
```

상기 구조에서 ControlBus는 외부에 노출되지 않으며, SDK는 Gateway로부터 불투명 스트림을 전달받아 구독한다(§14).
