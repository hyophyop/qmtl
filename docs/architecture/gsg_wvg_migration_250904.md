# GSG/WVG 마이그레이션 패키지 (초안)

아래는 **QMTL → GSG/WVG 아키텍처**로 전환할 때 쓸 수 있는 **풀스펙 문서 패키지**입니다.
바로 레포의 `/docs/adr/` 및 `/docs/spec/`에 붙여 넣어 사용하실 수 있도록 **RFC/ADR 스타일**, **스키마/DDL/API**, **마이그레이션 절차**, **운영/테스트 플랜**, **FAQ**까지 포함했습니다.

---

## Normative Addendum — 권장 문구(프로젝트 전역 합의용)

- 책임 경계(SSOT): GSG는 DAG Manager(Neo4j)의 불변 SSOT이고, WVG(WorldNodeRef/Validation/DecisionEvent)는 WorldService(월드 DB)의 가변 SSOT다. DAG Manager는 WVG를 저장·갱신하지 않으며, WorldService는 GSG를 변경하지 않는다.
- NodeID 규칙: NodeID는 Canonical(NodeType, interval, period, params(canonical & split), dependencies(sorted), schema_id, code_hash)의 바이트 직렬화를 해시한 값이다. 비결정적 필드는 캐논컬라이즈 입력에서 제외한다.
- 해시 알고리즘 정렬: 프로젝트 기본 해시는 BLAKE3로 한다. 문서·코드 전역에서 BLAKE3 접두사(`blake3:...`)를 사용하며, 변경은 ADR로 관리한다.
- 저장소 주석: SPEC‑002의 RDB DDL은 백업/분석용 레퍼런스이며 운영 SSOT는 GSG=Neo4j, WVG=WorldService DB이다.
- 결정 용어 분리: Stop/Pause/Resume/Quarantine는 DecisionEvent(scope 기본 world-local), WS 정책 판단은 DecisionEnvelope로 구분한다.

# 0) 문서 패키지 구성

* **ADR-001: 전역-월드 분리(“GSG/WVG”) 설계 결정**
* **SPEC-001: 개념/용어 사전(Glossary) + 레거시→신규 매핑표**
* **SPEC-002: 데이터 모델(JSON 스키마 & Postgres DDL)**
* **SPEC-003: API 스펙(REST/gRPC 이벤트 모델 포함)**
* **SPEC-004: 유효성 평가(EvalKey)와 상태 기계**
* **MIG-001: 마이그레이션 가이드(사전 점검→데이터 이행→롤백)**
* **OPS-001: 운영 플레이북(SLO/알람/런북)**
* **COMPAT-001: 호환 레이어(qmtl‑compat) 설계와 사용법**
* **TEST-001: 테스트 플랜(샘플 케이스/체크리스트)**
* **FAQ-001: 자주 묻는 질문**

아래에 **각 문서의 본문**을 제공합니다.

---

## ADR-001 — 전역-월드 분리(“GSG/WVG”) 설계 결정

**상태:** Accepted
**날짜:** 2025-09-04

### 문제 정의

* 동일한 전략/노드가 **여러 월드**에 제출될 수 있다.
* \*\*글로벌 DAG(중복 없음)\*\*을 유지하면서도, **유효성 평가·중단 결정은 월드별로 독립**이어야 한다.
* 기존 QMTL 저장소의 개념을 최대한 활용하면서도, 개발자 온보딩 복잡도를 억제해야 한다.

### 결정

1. **Global Strategy Graph (GSG)**: 전략과 노드를 \*\*내용 주소화(Content‑addressed)\*\*로 유일화한 전역 DAG. **중복 노드 없음**이 불변식.
2. **World View Graph (WVG)**: 각 월드에서 GSG를 **참조**해 붙인 **월드-로컬 오버레이**. 유효성/상태/결정은 **WVG에만 기록**.
3. **중단(Stop/Abort) 격리**: 기본 **scope=world-local**. 전파는 명시적 opt‑in일 때만.
4. **평가 캐시 키(EvalKey)**: `H(NodeID||WorldID||ContractID||DatasetFingerprint||CodeVersion||ResourcePolicy)`. 동일 노드라도 월드가 다르면 **평가 레코드 분리**.


### 근거

* 전역 중복 제거 + 월드별 독립성 확보.
* 변경 최소화(레거시 재사용) + 온보딩 비용 절감.

### 결과 영향

* 스토리지: 전역(불변)과 월드(가변)로 쓰기 경계 분리.
* 대시보드: 기본 뷰는 **월드 탭**. 전역 페이지는 집계(파생)만.

---

## SPEC-001 — 개념/용어 사전 + 레거시→신규 매핑표

### 핵심 용어

* **Node**: 연산자/규칙/데이터 소스 등 **내용 주소화**된 그래프 단위.
* **Strategy**: GSG에서 하나의 **루트 노드(StrategyRoot)**.
* **GSG**: 전 세계 공통 **전역 DAG**(중복 금지).
* **World**: 실행·평가 컨텍스트(거래소/자산군/체결규칙/수수료/데이터 스냅샷/리스크 정책).
* **WVG**: 특정 월드가 GSG를 바라보는 **오버레이 뷰**(월드-로컬 상태/유효성/결정 보관).
* **Validation**: `(WorldID, NodeID)` 단위의 **월드-로컬 검증**.
* **DecisionEvent**: stop/pause/resume/quarantine 등 **결정 이벤트**(기본 scope=world-local).

### 레거시 → 신규 매핑표

| 레거시(QMTL 레포 내 추정/변형 포함)                                        | 신규 개념                       | 매핑 규칙                                                |
| -------------------------------------------------------------- | --------------------------- | ---------------------------------------------------- |
| `StrategyGraph` / `Pipeline` / `Plan`                          | **Strategy (GSG 루트)**       | 루트 노드를 캐논컬라이즈 → `StrategyID=NodeID(root)`            |
| `Operator` / `Indicator` / `Transform` / `Rule` / `DataSource` | **Node (GSG)**              | 파라미터/의존성 **정규형 직렬화** 후 해시 → `NodeID`                 |
| `Edge` / `Dependency`                                          | **GSG Edge**                | GSG에만 저장(불변).                                        |
| `Environment` / `Context` / `MarketProfile` / `Venue`          | **World**                   | 월드 설정을 **버전 스냅샷**화 → `WorldID`                       |
| `Backtest` / `PaperTest` / `ValidationReport`                  | **Validation (WVG)**        | 결과는 **WVG**에 저장, 키는 **EvalKey**                      |
| `LiveRun` / `Execution`                                        | **WVG 상태 `running`**        | 월드-로컬 상태 기계 상에서 표현                                   |
| `Stop/Abort`                                                   | **DecisionEvent**           | 기본 `scope="world-local"`, 전파는 명시적                    |
| `RiskPolicy` / `Contract` / `RuleSet`                          | **ContractID (World 구성요소)** | World 스냅샷에 포함, EvalKey 구성요소                          |
| `DatasetVersion` / `DataSnapshot`                              | **DatasetFingerprint**      | World 스냅샷에 포함, EvalKey 구성요소                          |
| `ResourceProfile` / `Budget`                                   | **ResourcePolicy**          | EvalKey 구성요소(성능/자원 바뀌면 재평가)                          |
| `Universe`                                                     | **(선택) Node 또는 World**      | 시장 규정으로 고정이면 World, 전략 가변이면 Node(“UniverseSelector”) |
| `ExperimentID`                                                 | **EvaluationID/EvalKey**    | 동일 전략이라도 월드/데이터 다르면 상이                               |

> **권고:** 사용자 선호에 따라 *분리 가능한 모든 파라미터*는 Node.params에서 **개별 필드로 분리**하여 캐논컬라이즈(요구사항 반영).

---

## SPEC-002 — 데이터 모델

### JSON 스키마 (요지)

```json
{
  "Node": {
    "node_id": "blake3:...",              // content-addressed
    "node_type": "Operator|Source|Rule|Root",
    "schema_version": "v1",
    "params": { "...": "..." },           // 분리 가능한 파라미터는 모두 개별 필드
    "dependencies": ["blake3:...", "..."],
    "code_version": "git:abcd1234"
  },
  "World": {
    "world_id": "world:krx-spot-v2025.09.01",
    "contract_id": "policy:krx-baseline-v5",
    "market_config": { "tz": "Asia/Seoul", "lot": 1, "fees": "...", "slippage_model": "..." },
    "dataset_fingerprint": "lake:blake3:...",
    "risk_limits": { "...": "..." }
  },
  "WorldNodeRef": {
    "world_id": "world:...",
    "node_id": "blake3:...",
    "status": "unknown|validating|valid|invalid|running|paused|stopped|archived",
    "last_eval_key": "blake3:EvalKey",
    "annotations": { "budget": "...", "owner": "...", "notes": "..." }
  },
  "Validation": {
    "eval_key": "blake3:...",
    "world_id": "world:...",
    "node_id": "blake3:...",
    "result": "valid|invalid|warning",
    "metrics": { "pnl": 0.0, "sharpe": 1.2, "coverage": 0.93 },
    "timestamp": "2025-09-04T02:33:00Z"
  },
  "DecisionEvent": {
    "event_id": "uuid",
    "world_id": "world:...",             // REQUIRED if scope=world-local
    "node_id": "blake3:...",
    "decision": "stop|pause|resume|quarantine",
    "reason_code": "VAL_FAIL|RISK_TRIP|OP_INCIDENT|MANUAL",
    "scope": "world-local|multi-world|global", // default: world-local
    "propagation_rule": "none|same-contract|same-dataset|explicit-list",
    "ttl": "P0D|P7D|P30D",
    "timestamp": "..."
  }
}
```

### 월드별 도달성/비활성 에지

월드 정책으로 인해 특정 에지가 해당 월드에서 비활성화될 수 있다(예: 파생상품 금지, 데이터/리스크 정책). 이때 WVG는 “월드-로컬 에지 오버라이드”를 기록해 도달성·검증 범위를 월드별로 좁힌다.

```json
{
  "WvgEdgeOverride": {
    "world_id": "world:...",
    "src_node_id": "blake3:...",
    "dst_node_id": "blake3:...",
    "active": false,
    "reason": "DERIVATIVES_DISABLED|DATA_POLICY|MANUAL"
  }
}
```

> 참고: 아래 RDB DDL은 백업/분석 및 호환 계층 설계를 돕기 위한 레퍼런스입니다. 운영 SSOT는 DAG(GSG)=Neo4j, WVG(World/Validation/Decisions)=WorldService DB입니다.

### Postgres DDL (요지)

```sql
-- 전역(불변) 스토어
CREATE TABLE gsg_node (
  node_id text PRIMARY KEY,
  node_type text NOT NULL,
  schema_version text NOT NULL,
  params jsonb NOT NULL,
  dependencies text[] NOT NULL,
  code_version text NOT NULL
);
CREATE TABLE gsg_edge (
  src_node_id text NOT NULL REFERENCES gsg_node(node_id),
  dst_node_id text NOT NULL REFERENCES gsg_node(node_id),
  PRIMARY KEY (src_node_id, dst_node_id)
);

-- 월드(가변) 스토어
CREATE TABLE world (
  world_id text PRIMARY KEY,
  contract_id text NOT NULL,
  market_config jsonb NOT NULL,
  dataset_fingerprint text NOT NULL,
  risk_limits jsonb NOT NULL
);

CREATE TABLE wvg_world_node_ref (
  world_id text NOT NULL REFERENCES world(world_id),
  node_id text NOT NULL REFERENCES gsg_node(node_id),
  status text NOT NULL,
  last_eval_key text,
  annotations jsonb,
  PRIMARY KEY (world_id, node_id)
);

CREATE TABLE validation (
  eval_key text PRIMARY KEY,
  world_id text NOT NULL REFERENCES world(world_id),
  node_id text NOT NULL REFERENCES gsg_node(node_id),
  result text NOT NULL,
  metrics jsonb NOT NULL,
  timestamp timestamptz NOT NULL
);

-- 월드-로컬 에지 오버라이드(도달성 제어)
CREATE TABLE wvg_edge_override (
  world_id text NOT NULL REFERENCES world(world_id),
  src_node_id text NOT NULL REFERENCES gsg_node(node_id),
  dst_node_id text NOT NULL REFERENCES gsg_node(node_id),
  active boolean NOT NULL DEFAULT false,
  reason text,
  PRIMARY KEY (world_id, src_node_id, dst_node_id)
);

CREATE TABLE decision_event (
  event_id uuid PRIMARY KEY,
  world_id text,
  node_id text NOT NULL REFERENCES gsg_node(node_id),
  decision text NOT NULL,
  reason_code text NOT NULL,
  scope text NOT NULL DEFAULT 'world-local',
  propagation_rule text NOT NULL DEFAULT 'none',
  ttl interval NOT NULL DEFAULT '0',
  timestamp timestamptz NOT NULL
);

-- 유용 인덱스
CREATE INDEX idx_wvg_status ON wvg_world_node_ref(world_id, status);
CREATE INDEX idx_val_world_node_time ON validation(world_id, node_id, timestamp DESC);
CREATE INDEX idx_edge_override_world ON wvg_edge_override(world_id);
CREATE INDEX idx_decision_world_time ON decision_event(world_id, timestamp DESC);
```

> **쓰기 경계:** `gsg_*` 테이블은 **append-only**가 이상적(변경 시 신규 `node_id` 생성).

---

## SPEC-003 — API 스펙

### Submission과 바인딩(WSB)

용어 정의: WSB(WorldStrategyBinding)는 `(world_id, strategy_id)` 바인딩 레코드다. `POST /submit` 호출 시 `world_ids[]`의 각 항목에 대해 WSB가 생성되며, 구현상으로는 해당 월드의 WVG에 `WorldNodeRef(root)`가 생성/업데이트된다. 동일 바인딩은 멱등 처리한다.

### REST (요지)

```http
POST /submit
Content-Type: application/json
{
  "strategy_id": "blake3:...",        // StrategyRoot NodeID
  "world_ids": ["world:ko-spot-v2025.09.01","world:us-fut-v2025.09.01"]
}
→ 202 Accepted
```

```http
GET /status?strategy_id=blake3:...&world_id=world:ko-spot-v2025.09.01
→ 200 OK
{
  "world_id": "world:...",
  "strategy_id": "blake3:...",
  "status": "stopped",
  "last_eval": { "result": "invalid", "eval_key": "blake3:..." }
}
```

```http
POST /decision
{
  "world_id": "world:ko-spot-v2025.09.01",
  "node_id": "blake3:... (strategy root)",
  "decision": "stop",
  "scope": "world-local",             // default
  "reason_code": "VAL_FAIL"
}
→ 201 Created
```

### gRPC 이벤트 (요지)

* Topic: `decision.events.v1`
* Message: `DecisionEvent` (SPEC‑002와 동일 필드)
* **정책:** `scope=world-local`이 아닌 메시지는 승인 워크플로를 통과해야 소비됨.

---

## SPEC-004 — 유효성 평가와 상태 기계

### EvalKey

```
EvalKey = H(
  NodeID
  || WorldID
  || ContractID
  || DatasetFingerprint
  || CodeVersion
  || ResourcePolicy
)
```

* 위 요소 **하나라도 변경** 시 재평가.
* Node 파라미터는 **정규형 직렬화**로 NodeID에 흡수.

### 상태 기계(월드-노드 단위)

`unknown → validating → (valid | invalid)`
`valid → (running | schedulable)`
`running → (paused | stopped)`
`invalid → (fix 후 validating 재시도)`

> **격리 원칙:** 한 월드에서 `stopped`여도 다른 월드의 상태에는 **영향 없음**.

---



## MIG-001 — 마이그레이션 가이드

### 1. 범위

* 레거시 QMTL 레포 내 **전략/노드/그래프/환경/검증/중단** 관련 모든 데이터와 코드.

### 2. 사전 점검(Pre‑flight)

* [ ] 레거시 **노드 직렬화 포맷**에서 비결정적 필드(타임스탬프/시드 등) 제거 가능?
* [ ] **파라미터 분리**가 가능한가(롱/숏/레버리지/수수료/슬리피지 등 개별 필드화)?
* [ ] 레거시 “환경/마켓/시장구성”을 **버전 스냅샷**으로 고정 가능?
* [ ] 데이터 소스별 **DatasetFingerprint** 계산 경로 확보?
* [ ] 레거시 “중단/정지” 이벤트에 \*\*범위 개념(scope)\*\*이 없는지 확인(있다면 맵핑 규칙 수립).

### 3. 데이터 이행 절차(안전 실행 순서)

**Step A — GSG 백필(전역 DAG):**

1. 레거시 노드들을 **캐논컬라이즈**:

   * 파라미터를 개별 필드로 정렬/정규화(숫자 스케일, enum 표준화).
   * 의존성 정렬(사전식) → 직렬화 → `NodeID = blake3(canonical)` 생성.
2. `gsg_node`, `gsg_edge`에 **upsert**(이미 존재하면 skip).
3. 전략 루트는 **StrategyRoot로 태깅** → `StrategyID=NodeID(root)`.

**Step B — World 스냅샷 생성:**

1. 레거시 환경/시장설정/리스크/수수료/슬리피지/거래시간을 모아 **World 객체**로 스냅샷.
2. 데이터 소스 버전/기간으로 **DatasetFingerprint** 생성.
3. `world` 테이블에 insert(`WorldID` = 의미 있는 버전 문자열 권장).

**Step C — WVG 오버레이 구축:**

0. (정의) `WSB(WorldStrategyBinding)` = `(world_id, strategy_id)` 바인딩. 이하 단계에서 각 제출 이력마다 WSB를 생성한다(멱등).

1. 제출 이력에 따라 `(world_id, strategy_id)`로 **WorldNodeRef** 생성.
2. 초기 상태 `unknown` → `validating`(큐잉).

**Step D — Validation 이행:**

1. 레거시 백테스트/평가 결과를 EvalKey 규칙으로 재키잉.
2. `validation` 테이블에 insert.
3. 최신 결과에 따라 `wvg_world_node_ref.status` 업데이트.

**Step E — DecisionEvent 이행:**

1. 레거시 stop/abort 기록을 **scope=world-local**로 기본 변환.
2. 전파 의도가 명시된 경우에만 `scope=multi-world|global`과 `propagation_rule` 매핑.
3. TTL을 부여하여 영구 오염 방지(`P0D`는 무제한).

### 4. 코드 마이그레이션(호환 레이어 병행)

* `qmtl_compat.StrategyGraph` → `gsg.StrategyRoot` 어댑터
* `qmtl_compat.Environment` → `world.World` 스냅샷 빌더
* `qmtl_compat.Backtest.run()` → `evaluation.enqueue(world_id, node_id)`로 리라우팅
* `qmtl_compat.stop()` → `decision.post(scope='world-local', ...)`

> **권장:** `qmtl-compat` 패키지는 **2개 마이너 버전** 동안 유지 후 폐기(아래 COMPAT-001 참조).

### 5. 대시보드 전환

* 전역 페이지: **월드별 카드 병렬 표시**, 전역 경고는 “사건 수/영향 월드 수” 집계만.
* 월드 탭: 상태/유효성/결정 타임라인 **전부 표출**.

### 6. 성능/스토리지 고려

* `gsg_node/node_id`는 **PK+압축**(BLAKE3 32바이트 권장).
* Validation 메트릭은 **jsonb**로 저장하되, 쿼리용 칼럼(예: `sharpe`, `pnl`)은 **생성 칼럼**으로 보강.

### 7. 롤백 계획(극단 시나리오 포함)

* **Extreme:** GSG 캐논컬라이저 오류로 NodeID 폭증
  → 롤백: 새 `gsg_*` 테이블을 **트랜잭션 스냅샷** 전환 전까지 shadow로 유지, 스위치 실패 시 포인터 되돌림.
* **Extreme:** 잘못된 전파로 다수 월드 중단
  → 모든 `scope!='world-local'` 이벤트 **즉시 quarantine** 후, 승인 워크플로 재검토.
* **Moderate:** DatasetFingerprint 누락
  → 해당 월드 전부 `validating`으로 강등, 재평가 큐 재생성.

### 8. 마이그레이션 체크리스트(요약)

* [ ] GSG 중복 없음 보장(캐논컬라이즈 테스트 통과)
* [ ] WorldID가 **버전 스냅샷**에 매핑됨
* [ ] EvalKey 모든 요소 포함(특히 DatasetFingerprint/ContractID)
* [ ] scope 기본값이 world-local로 강제
* [ ] 대시보드 격리와 집계 동작 확인

---

## OPS-001 — 운영 플레이북

**SLO**

* 제출→첫 평가까지 p95 **< 10분**
* 전역 중단 전파 승인 대기 p95 **< 5분**

**알람 예시**

* `GSG_NODE_DUP_RATE > 0.5%` (캐논컬라이즈 이슈 의심)
* `SCOPE_NON_LOCAL_DECISIONS > 0` (비상 점검 필요)

**지표 예시**

* 전역 노드 재사용도(Reuse%)

**런북**

1. **노드 중복 급증**: 캐논컬라이저 버전 고정 → 재해시 dry‑run → shadow 테이블 비교.
2. **월드 대량 invalid**: 최근 데이터 지문 변경 확인 → 재평가 큐 우선순위 조정.
3. **전파 사고**: 해당 이벤트 quarantine → 승인 로그 리뷰 → 필요시 TTL 0으로 무효화.

---

## COMPAT-001 — 호환 레이어(qmtl‑compat)

**목표:** 레거시 코드가 큰 수정 없이 신규 스토어를 사용하도록 어댑터 제공.

**구성**

* `StrategyGraphAdapter`: `LegacyStrategy` → `StrategyRoot(NodeID)`
* `EnvironmentAdapter`: 레거시 환경 → `World` 스냅샷 빌더
* `BacktestAdapter`: `run()` 호출을 `evaluation.enqueue(...)`로 라우팅
* `DecisionAdapter`: `stop()` → `DecisionEvent(scope='world-local')`

**수명 주기**

* `vX+1`, `vX+2`까지 유지 → `vX+3`에서 제거(사전 Deprecation Notice).

---

## TEST-001 — 테스트 플랜

**단위 테스트**

* 캐논컬라이즈: 동일 의미 표현 → 같은 `NodeID`, 비결정적 필드 포함 시 **다른** `NodeID`가 나오지 않음.
* EvalKey: 요소 변경마다 키가 달라짐.

**통합 테스트**

* 동일 전략을 2개 월드에 제출: A에서 `invalid→stop`, B는 `running` 유지.
* 데이터 지문 변경 시 상태 `validating` 회귀 및 재평가 캐시 무효화.

**성능 테스트**

* 10만 노드/100만 에지: GSG 삽입 p95 < 5분(병렬 인서트/배치 해시).

**체크리스트**

* [ ] 전파(scope) 승인 플로가 없는 이벤트는 소비되지 않음
* [ ] 대시보드 월드 탭과 전역 집계가 상충 없이 표기됨

---

## FAQ-001 — 자주 묻는 질문

**Q. 왜 `Universe`를 World가 아니라 Node로 두는 경우가 있나요?**
A. 거래소 상장 규칙 등 **시장 규범**이면 World에 고정(재현성↑). 전략이 **동적 선택**한다면 Node(“UniverseSelector”)로 두어 전략 버전에 귀속.

**Q. 레버리지/롱·숏/수수료 등 파라미터는 어디에?**
A. 모두 **Node.params의 개별 필드**로 분리 → 캐논컬라이즈에 포함. (요구사항: “분리 가능한 모든 파라미터 개별 분리”)

**Q. 동일 노드인데 리소스 한도만 바꿨을 때 재평가가 필요한가요?**
A. 예. `ResourcePolicy`는 EvalKey 구성요소입니다. 결과가 달라질 수 있으므로 재평가합니다.

---

# 부록 A — 캐논컬라이즈 규칙(발췌)

1. 키 정렬(JSON canonical form), float 정밀도 고정, enum은 스키마 명세값만 허용.
2. 무의미 공백/코멘트 제거.
3. 의존성 리스트 사전순 정렬.
4. 파일/아티팩트는 **내용 해시로 대체**(경로 금지).
5. 난수 시드/타임스탬프/런타임 환경 변수는 **NodeID 입력에서 제외**.

---

# 부록 B — 마이그레이션 실행 예(요지, pseudo)

```bash
# 1) GSG 백필
qmtl migrate gsg-backfill \
  --legacy-nodes dump/legacy_nodes.jsonl \
  --out gsg_node,gsg_edge

# 2) World 스냅샷 생성
qmtl migrate world-snapshot \
  --env dump/environments.yaml \
  --dataset-fp dump/datasets.yaml

# 3) Validation 이행
qmtl migrate validations \
  --legacy-backtests dump/backtests.parquet

# 4) Decision 이행
qmtl migrate decisions \
  --legacy-decisions dump/stops.jsonl --default-scope world-local
```

---

# 부록 C — 예시 아키텍처 다이어그램(ASCII)

```
         +---------------------------+
         |        Global DAG         |
         |         (GSG)             |
         |  Node/Edge (append-only)  |
         +-------------+-------------+
                       |
                       | reference only
      +----------------+-----------------+
      |                                  |
+-----v-----+                      +-----v-----+
|  World A  |                      |  World B  |
|  (WVG-A)  |                      |  (WVG-B)  |
| Validation|                      | Validation|
| Decisions |                      | Decisions |
+-----------+                      +-----------+
   stop(S) A                            run(S) B
 (scope=local)                       (independent)
```

---

## 적용 요약

* **전역 중복 제거**는 GSG가 담당, **평가/중단 격리**는 WVG가 담당합니다.
* **레거시 개념은 매핑표**에 따라 변환하고, **qmtl‑compat**로 이행 기간을 부드럽게 넘기세요.
* **EvalKey**로 월드별 재현성을 강제하고, **scope 기본값**을 world‑local로 고정하여 사고 전파를 방지합니다.

원하시면 위 문서들을 **마크다운 파일로 분할**해 드리거나, 레포 구조(`/docs/spec/*.md`)에 맞춘 목차/사이드바까지 포함한 버전으로 바로 제공하겠습니다.
