# Seamless 데이터 물질화 설계: DAG 격리 실행

!!! warning "Status: draft"
    이 문서는 초안 상태입니다. 구현 과정에서 세부 동작과 API가 변경될 수 있습니다.

## 핵심 아이디어

**DAG를 Core Loop에서 격리하여 실행**하는 것이 본 설계의 핵심이다.

- **Core Loop (live/paper)**: `Runner.submit` → World/activation 흐름, `as_of = now` (실시간)
- **Materialize**: DAG를 격리된 환경에서 **지정된 범위(start/end)** 로 replay

```
┌─────────────────────────────────────────────────────────┐
│              SeamlessDataProvider (공통 엔진)            │
└─────────────────────────┬───────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          │                               │
   Core Loop 실행                  격리 실행 (Materialize)
   Runner.submit(...)              MaterializeSeamlessJob(...)
   as_of = now                     as_of = start..end
          │                               │
          ▼                               ▼
   WS/activation/allocations       노드별 물질화 저장
```

### 왜 start/end가 필요한가?

DAG에 wiring된 `SeamlessDataProvider`는 **start/end를 저장하지 않는다**:

- `SeamlessDataProvider.fetch(start, end, ...)` — 파라미터로 받음
- `DataPresetSpec` — interval_ms, sla_preset만 있고 범위 없음
- Core Loop에서는 Runner가 `as_of = now`를 암묵적으로 결정

따라서 **과거 데이터 사전 계산(물질화)**이 목적이라면 범위는 외부에서 제공해야 한다.

## API

```python
# DAG + 범위만 입력
job = MaterializeSeamlessJob(
    strategy=MyStrategy,   # DAG (모든 설정 자동 추출)
    start=1700000000,      # 범위 시작
    end=1700100000,        # 범위 종료
)
report = await job.run()
```

### 자동 추출 항목

| 항목 | 추출 소스 |
|------|-----------|
| `interval` | 각 노드의 `node.interval` |
| `period` | 각 노드의 `node.period` |
| `preset` | `StreamInput.history_provider.preset` |
| `history_provider` | `StreamInput.history_provider` |

### 입력

| 입력 | 설명 |
|------|------|
| `strategy` | 물질화할 DAG |
| `start` | 시작 타임스탬프 |
| `end` | 종료 타임스탬프 |

## 실행 흐름

```
1. Strategy 인스턴스화 → 노드 그래프 구성
2. Compute-only 컨텍스트 (live 구독/WS 호출 차단)
3. 토폴로지 정렬 → 실행 순서 결정
4. StreamInput 워밍업 → SeamlessDataProvider.fetch(start, end)
5. 노드 순차 실행 → compute_fn 호출 및 저장
6. 리포트 생성 → fingerprint/coverage 통합
```

## 출력

```python
@dataclass
class MaterializeReport:
    coverage_bounds: tuple[int, int]  # 물질화된 범위
    node_count: int                   # 물질화된 노드 수
```

> fingerprint 등 내부 구현 세부사항은 자동 캐시에서 사용되며 사용자가 직접 다룰 필요 없음.

## 자동 캐시

**동일 DAG + 동일 범위 = 캐시 히트** (재계산 없이 로드)

```python
# 첫 실행: 계산 후 저장
job = MaterializeSeamlessJob(MyStrategy, start=T0, end=T1)
await job.run()

# 재실행: 자동 캐시 히트 (재계산 없음)
job = MaterializeSeamlessJob(MyStrategy, start=T0, end=T1)
await job.run()  # 즉시 완료
```

사용자는 fingerprint나 storage 경로를 관리할 필요 없음.

## 비교

| 항목 | Core Loop | Materialize |
|------|-----------|-------------|
| 입력 | Strategy + world | Strategy + start/end |
| 범위 | `as_of = now` | 명시적 start/end |
| 모드 | live/backtest | compute-only |
| 출력 | WS/activation | fingerprint/coverage 리포트 |
| 저장 | 런타임 캐시 | 영구 저장 |

## 테스트

```python
def test_materialize_and_cache():
    # 첫 실행
    job = MaterializeSeamlessJob(MyStrategy, start=T0, end=T1)
    r1 = await job.run()
    assert r1.node_count > 0
    
    # 재실행: 캐시 히트
    r2 = await MaterializeSeamlessJob(MyStrategy, start=T0, end=T1).run()
    assert r2.coverage_bounds == r1.coverage_bounds
```
