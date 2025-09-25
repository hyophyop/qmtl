# Seamless Data Provider v2 재설계 검토

아래는 \*\*기존 설계안(Seamless 중심, history\_coverage SSOT, AutoBackfiller, 캐시/락 일원화)\*\*과 \*\*설계 검토안(정합성 계층, 분산 단일 비행, SLA/타임아웃, 관측성, 테스트/운영 강화)\*\*을 **최대 공약수 + 보완 요소**로 통합한 **재설계 v2**입니다.
핵심은 **단일 진입점 + 표준화된 정규화/메타데이터 + 분산 단일 비행 + 전략별 SLA**입니다.

---

## 0) TL;DR — 무엇이 바뀌나

* **단일 진입점 유지**: `SeamlessDataProvider` 그대로 표준화(공개 API).
* **정합성 계층 추가**: 모든 소스 결과를 **Schema/Time 정규화 파이프라인**으로 통일 → 컬럼/타임존/샘플링/중복/품질 플래그 표준화.
* **분산 단일 비행**: 멀티 인스턴스에서 백필 범위 충돌을 막는 **Backfill Coordinator(락/큐/리스 기반)** 도입.
* **전략별 SLA/타임아웃 규약**: FAIL\_FAST/PARTIAL/SEAMLESS별 **대기·폴백·에러 노출**을 명문화(요청 레벨 파라미터로 독립 제어).
* **응답 메타데이터 표준**: `HistoryResult = {df, meta}`로 반환(coverage/missing/수행전략/품질·워터마크/소스별 기여/ SLA 리포트 포함).
* **관측성 패키지**: OpenTelemetry 트레이싱 + 구조화 로그 + 표준 메트릭 & 알림 룰.
* **테스트/운영 강화**: 품질/지연/장애 시나리오, 실패 주입, 카나리 백필, 롤백·재처리 절차 구체화.
* **SchemaRegistry 거버넌스**: 노드/전략별 스키마·정규화 룰을 버전 관리하고 strict 모드/드라이런을 지원.
* **운영 가드레일**: SLA 템플릿, 대시보드, 백필/스키마 변경 승인 플로우 등 운영 책임을 명시.

---

## 1) 비교 결과와 채택 결정

| 항목            | 기존 설계안 장점                              | 검토안 보완       | **재설계 v2 채택**                 |
| ------------- | -------------------------------------- | ------------ | ----------------------------- |
| 진입점/전략        | `SeamlessDataProvider` + `Strategy` 1급 | —            | **유지**                        |
| 커버리지 수학       | `history_coverage` SSOT                | —            | **유지**                        |
| 소스 우선순위       | CACHE→STORAGE→BACKFILL→LIVE            | —            | **유지 + 요청별 재정의 허용**           |
| AutoBackfill  | 표준 인터페이스                               | —            | **유지**, 브리지로 구구조 호환           |
| 정합성(스키마/타임라인) | (미명시)                                  | 정규화 파이프라인 제안 | **채택 (Conformance Layer 추가)** |
| 분산 단일 비행      | (프로세스 내)                               | Redis/PG 락·큐 | **채택 (Coordinator 모듈)**       |
| PARTIAL 메타정보  | (미명시)                                  | 메타데이터 요구     | **채택 (HistoryMeta 표준)**       |
| SLA/타임아웃      | (암묵/부분)                                | 전략별 명문화      | **채택 (SLA Matrix)**           |
| 관측성           | 메트릭 일부                                 | OTel/로그/알림   | **채택 (Observability 패키지)**    |
| 테스트/운영        | 범용·성능                                  | 품질·실패주입·카나리  | **채택 (세분화 테스트 & 운영 체크리스트)**   |

---

## 2) 목표 아키텍처

```
┌──────────────────────────────────────────────────────────────────┐
│                       SeamlessDataProvider (Public API)          │
│ read / ensure / coverage                                         │
│  - Strategy (FAIL_FAST | AUTO_BACKFILL | PARTIAL_FILL | SEAMLESS)│
│  - SLAPolicy (latency budgets, timeouts, retry/fallback)         │
│  - CoverageCacheOwner (single)                                   │
│  - BackfillCoordinator (distributed single-flight)               │
│  - history_coverage (SSOT: merge/missing/intersect/strict)       │
│  - Conformance Pipeline (schema/time/quality normalization)      │
└───────────▲───────────────▲────────────────────▲─────────────────┘
            │               │                    │
      DataSource[*]     AutoBackfiller      Observability
  (CACHE/STORAGE/       (plug-in)           (OTel, metrics,
   BACKFILL/LIVE)                            logs, alerts)
```

---

## 3) 공개 API (최소·분리 가능한 파라미터 유지)

```python
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Dict, Tuple, Optional
import pandas as pd

class Strategy(Enum):
    FAIL_FAST = "fail_fast"
    AUTO_BACKFILL = "auto_backfill"
    PARTIAL_FILL = "partial_fill"
    SEAMLESS = "seamless"

@dataclass
class SLAPolicy:
    max_wait_storage_ms: int | None = None
    max_wait_backfill_ms: int | None = None
    max_wait_live_ms: int | None = None
    retry_backoff_ms: int | None = None
    total_deadline_ms: int | None = None

@dataclass
class Watermarks:
    event_time_low: int | None = None  # LWM
    event_time_high: int | None = None # HWM

@dataclass
class HistoryMeta:
    strategy: Strategy
    strict: bool
    request_id: str
    coverage_ranges: "RangeSet"
    missing_ranges: "RangeSet"
    source_contributions: Dict[str, "RangeSet"]  # per-source filled ranges
    watermarks: Watermarks
    sla_report: Dict[str, object]                 # waits, timeouts, retries
    quality_summary: Dict[str, object]           # e.g., gap_count, ooo_count
    notes: Tuple[str, ...] = ()

@dataclass
class HistoryResult:
    df: pd.DataFrame
    meta: HistoryMeta

class DataProvider(Protocol):
    async def coverage(self, node_id: str, interval: str) -> "RangeSet": ...
    async def ensure_available(
        self, node_id: str, interval: str, start: int, end: int,
        *, strategy: Strategy = Strategy.AUTO_BACKFILL,
           strict: bool = False,
           source_priority: Tuple[str, ...] = (),
           sla: Optional[SLAPolicy] = None,
    ) -> "AvailabilityResult": ...
    async def read(
        self, node_id: str, interval: str, start: int, end: int,
        *, strategy: Strategy = Strategy.SEAMLESS,
           strict: bool = False,
           source_priority: Tuple[str, ...] = (),
           sla: Optional[SLAPolicy] = None,
           return_meta: bool = True,
    ) -> HistoryResult | pd.DataFrame: ...
```

> **원칙**
>
> * 모든 정책은 **독립 파라미터**(strategy/strict/source\_priority/SLA)로 제어.
> * 기본 간격 규약: **UTC, 절반열림 \[start, end)**, interval 경계 정렬 강제.
> * `return_meta=False`이면 기존 호환을 위해 DataFrame만 반환.

---

## 4) Conformance Pipeline (데이터 정합성 계층)

**역할**: 소스별 편차를 **표준 스키마/타임라인**으로 정규화하고, 품질 플래그·마킹을 일괄 부여.

1. **스키마 정규화**

   * 표준 컬럼 세트 정의(예: 시계열 금융 OHLC: `ts,event_time,open,high,low,close,volume,...`)
   * 타입 강제(float64/int64/category), 컬럼 리네이밍/드랍 룰, missing sentinel(`NaN`/`<NA>`).
   * **스키마 호환성 계약**(Schema Contract): 추가 컬럼은 **뒤에 부가**, 필수 컬럼은 불변.
   * 노드/전략별 스키마는 버전 관리되는 `SchemaRegistry`에 저장하고, 배포 전/런타임에 **호환성 검사**(required/optional/experimental 필드 구분).

2. **시간 정규화**

   * 모든 입력을 UTC로 변환 → `event_time` 기준.
   * interval 경계에 **라운딩/버킷팅**(예: 1m bar).
   * **워터마크**(event-time LWM/HWM) 산출, out-of-order 허용 윈도우(예: 2×interval) 내 흡수.

3. **샘플링/롤업 규칙**

   * 같은 bar 내 다수 표본 병합: open=first, high=max, low=min, close=last, volume=sum, vwap=∑(p·v)/∑v.
   * 충돌 시 **Source Priority 우선**(기본), 필요시 `version`/`ingest_time` 기반 LWW 정책 선택 가능.

4. **중복/결측/품질 플래그**

   * 행 수준 메타: `__source`, `__ingest_at`, `__backfill_job_id`, `__flags(bitset)`
   * 플래그 예: `BACKFILLED`, `LIVE`, `FWD_FILLED`, `OUT_OF_ORDER`, `ADJUSTED`, `PARTIAL_BAR`.

5. **출력 보증**

   * **정렬(시간 오름차순)**, **유일 키(node\_id, interval, event\_time)** 보장.
   * `strict=True` 시 **expected bar count 일치** 검증 및 위반 시 오류/레드 플래그.

6. **컨피그 & 리포트 연동**

   * 정규화 과정에서 생성된 품질 지표/경고를 `ConformanceReport`로 묶어 `HistoryMeta.quality_summary`에 직결.
   * `SchemaRegistry`/정규화 룰은 코드리스(config-driven) 변경 가능성을 염두에 두고, 변경 시점별 워터마크와 함께 **감사 로그** 남김.

---

## 5) 분산 단일 비행(Backfill Coordinator)

**목표**: 다중 인스턴스/워크커에서 동일 범위 백필 중복을 제거하고 **idempotent**하게 처리.

* **Claim/Lease 모델**

  * **키**: `(node_id, interval, aligned_window)`
  * 저장소: Redis(SET NX + TTL + token), 또는 Postgres **advisory lock** + `backfill_jobs` 테이블
  * 상태: `PENDING → RUNNING(lease_until) → SUCCEEDED/FAILED/EXPIRED`
  * **고유 제약**: `(node_id, interval, window_start, window_end)` 유니크 → 중복 실행 억제
  * `aligned_window`는 coverage에서 정의한 canonical 윈도우 크기(예: interval × chunk_size)를 사용하고, 서버 측에서 오버랩 제거/재정렬.
  * Claim에는 마지막 커버리지 etag/version을 포함해 **stale claim**을 조기에 차단.

* **작업 수명주기**

  1. ensure/read에서 missing 계산
  2. Coordinator에 **claim** 시도 → 성공 시 **lease** 부여
  3. AutoBackfiller 실행(재진입 가능·idempotent)
  4. 성공 범위 기록 + coverage etag/version 증가 + 캐시 invalidate
  5. 부분 성공 시 `completed_ranges`/`remaining_ranges`를 분리 저장해 다음 claim이 잔여 범위만 처리하도록 유지

* **회복/만료**

  * `lease_until` 초과 시 **재청구 가능**(토큰 비교·CAS)
  * 실패 누적 시 **지수 백오프**, 알림 발송
  * 장애 구간은 자동으로 `quarantine` 태그를 부여하고, 운영자가 재시도/건너뛰기 여부를 선택 가능하도록 API 제공

* **Coverage 동기화**

  * Backfiller는 `history_coverage`에 **원자적 merge**를 요청하고, 실패 시 lease를 즉시 반납.
  * 커버리지 업데이트는 `RangeSet` 기준 diff를 저장해 추후 감사/재처리 시 **원인 추적** 가능하도록 보존.

---

## 6) 전략별 SLA/타임아웃 매트릭스(프로파일 예시)

| 전략             | 기본 폴백 순서                                        | 대기 한도(권장 범위)                              | 실패/부분 규약                                                 |
| -------------- | ----------------------------------------------- | ----------------------------------------- | -------------------------------------------------------- |
| FAIL\_FAST     | CACHE→STORAGE                                   | storage ≤ O(50–150ms)                     | 결측 즉시 오류(메타 포함)                                          |
| PARTIAL\_FILL  | CACHE→STORAGE→(BACKFILL async)                  | total ≤ O(300–800ms)                      | 채워진 부분만 반환 + `missing_ranges` 메타 필수                      |
| AUTO\_BACKFILL | CACHE→STORAGE→BACKFILL(동기 재시도 1회)               | backfill ≤ O(2–10s), total ≤ SLA.deadline | 실패 시 PARTIAL 또는 오류(정책화)                                  |
| SEAMLESS       | CACHE→STORAGE→BACKFILL(동기, 범위 크기 한도 내)→LIVE(소창) | small-miss: ≤ O(1–5s), large-miss: detach | large-miss는 **detached backfill** 후 즉시 PARTIAL 반환 가능(옵션) |

> 값은 환경별 튜닝이 전제이며, **SLAPolicy**로 요청/서비스/환경 레벨에서 재정의합니다.

추가 규약:

- `SLAPolicy`는 동기 백필 허용 범위를 `max_sync_gap_bars`(또는 시간 기반)로 제한해, 긴 범위는 자동으로 PARTIAL + 비동기 백필로 전환합니다.
- SLA 위반 시 응답 메타에 `sla_report.violation`을 채우고, 호출자는 전략과 무관하게 후속 플로우에서 **일관된 조치**(재시도/무시)를 취할 수 있습니다.
- 전략별 기본 구성을 서비스 템플릿(YAML 등)으로 제공해 운영 환경 간 편차를 줄이고, 배포 시 drift 감지를 수행합니다.

---

## 7) 관측성(Observability) 패키지

* **Tracing (OpenTelemetry)**

  * Span 명: `history.read`, `coverage.compute`, `backfill.claim`, `backfill.run`, `datasource.read`, `lock.acquire`
  * 공통 속성: `request_id`, `node_id`, `interval`, `start`, `end`, `strategy`, `strict`, `source`, `missing_count`, `wait_ms`, `timeout`
  * 컨텍스트 전파: API → 내부 모듈 → 백필 작업자
  * `HistoryMeta.request_id`와 Trace/Span ID를 링크해 downstream 처리(예: 전략 엔진)에서도 **관측성 상속**이 가능하도록 Baggage에 주입

* **Metrics**

  * `history.read.latency_ms`, `history.read.partial_ratio`, `history.coverage.cache.hit|miss`
  * `backfill.queue_length`, `backfill.duration_ms`, `backfill.success|fail.count`
  * `lock.contention.count`, `job.retries.count`
  * 태그: `source`, `strategy`, `strict`, `interval`
  * 파생 SLO 지표: `history.read.success_rate`, `sla.violation.ratio`, `backfill.single_flight.collision`

* **Logs (JSON 구조화)**

  * 필드: 위 트레이스 속성 + `error_kind`, `exception`, `sla_violation`
  * **경보 룰**(예): partial\_ratio↑, lock\_contention↑, backfill.duration p95↑, SLA 위반율↑

* **대시보드 & 실행 가이드**

  * 표준 Grafana(또는 대응 도구) 대시보드를 정의하고, 릴리즈 별 변경 시 changelog를 남깁니다.
  * 경보 대응 플레이북: SLA 위반 → 원인 추적 → 임시 조치(전략 강등, 백필 중단) → 후속 RCA 순서를 문서화.

---

## 8) 테스트/검증 계획(구체화)

1. **수학/범위 성질**: `history_coverage` 결합/교환/멱등(Hypothesis)
2. **정합성**:

   * 시간대/샘플링 불일치 → 정규화 후 일치성 검증
   * 중복/역정렬/ooo 주입 → 플래그/정렬/키 유일성 확인
3. **스키마 레지스트리 회귀**: `SchemaRegistry` 스냅샷과 실데이터를 대조해 필수 필드 누락/타입 변화를 사전 탐지, 호환성 위반 시 배포 차단
4. **전략 행태**: 전략×SLA 조합별 **반환/메타** 일관성
5. **실패 주입**: 소스 타임아웃/오류/부분 데이터, 분산 락 타임아웃, backfill 실패/재시도
6. **카나리 백필**: 신규 백필 구현을 소수 심볼/구간에만 적용 → 결과 diff/품질 기준치 통과 시 확장
7. **성능/부하**: p50/p95/p99 지연, 락 경합, 큐 대기, 캐시 TTL 민감도
8. **데이터 품질 규칙**: 음수 volume, 비정상 점프, 역주행 가격 감지(룰·Z-score)
9. **회복력**: lease 만료/재청구, 롤백 후 재처리, 알림→사람 개입 루프
10. **관측성 회귀**: 주요 API에 대한 트레이스/메트릭/로그가 누락되지 않았는지 자동 검사(예: Metric golden set, trace schema validator)

---

## 9) 마이그레이션 & 배포/운영

* **PR 분할**

  0. `SchemaRegistry`/Conformance 설정 스키마 정의 + 마이그레이션 경로 문서화(기존 소스 매핑 표 작성)
  1. 범위 연산 SSOT화(기존 `_merge_ranges` 제거), `HistoryResult`/`HistoryMeta` 도입(옵션 플래그)
  2. Conformance Layer 도입 + 소스 어댑터 얇게 정리
  3. Backfill Coordinator + CoverageCacheOwner 재정립(분산 락/큐 플러그인)
  4. SLAPolicy/Observability/테스트 확장 + 문서/MIGRATION

* **런타임 가드/플래그**

  * `enable_coordinator`, `enable_detached_backfill`, `return_meta_default`, `strict_default`
  * 긴급 **Kill-Switch**: `DISABLE_BACKFILL`, `FORCE_FAIL_FAST`
  * `schema_registry_strict_mode` 토글로 새 스키마 검증을 카나리 방식으로 단계적으로 강화

* **롤백/재처리**

  * 릴리즈 태그별 **MIGRATION.md**: 스키마/캐시 키/락 키 변경 공지
  * 실패 시: 플래그로 백필 비활성화→캐시 강제 무효화→구버전 경로 복귀
  * 재처리: `backfill_jobs` 상태 기준 재시작/스킵(idempotent)

* **운영 필수 준비물**

  * Coordinator 백엔드(Redis/PG)와 SchemaRegistry 저장소에 대한 **용량·백업 정책**을 명시하고 SLO와 연결.
  * 운영팀이 참고할 **노드/소스 매핑 표**와 접속 권한 정책을 함께 배포.

---

## 10) 위험도(극단 포함)와 대응

* **부정적(최악)**: 분산 락 오동작으로 대규모 중복 백필/경합 → *고유 제약 + lease 토큰화 + 만료 재청구 + 알림/감지 규칙*
* **중립**: 초기 성능 동일, 관측성 확대로 병목 파악 용이 → *SLA 튜닝 주기 도입*
* **긍정적**: 중복 백필 제거·정합성 보장·운영 가시성↑ → p95 지연·오류율↓, 데이터 품질↑
* **운영 리스크**: SchemaRegistry 업데이트나 SLA 템플릿 배포가 잘못되면 단일 진입점이 즉시 실패할 수 있으므로, **이중 승인 + 드라이런 지원 도구**를 필수화.

---

## 11) 수용 기준 (Definition of Done)

1. 전 범위/커버리지 연산이 `history_coverage`만 사용
2. `SeamlessDataProvider` 단일 공개 진입점 + 전략/strict/SLA/우선순위 **독립 파라미터**
3. Conformance Pipeline로 **스키마/시간/품질 표준화** 및 행 플래그 주입
4. Backfill Coordinator로 **분산 단일 비행** 보장(고유 제약+리스)
5. `HistoryResult.meta`로 **coverage/missing/워터마크/SLA/품질** 제공
6. OTel 트레이스 + 구조화 로그 + 메트릭/알림 룰 적용
7. 테스트 스위트 통과(수학/정합성/실패주입/성능/카나리)
8. MIGRATION/운영 문서 완료 + deprecation 경고 적용
9. `SchemaRegistry`/Conformance 설정이 버전 관리되고, Strict 모드에서 사전 호환성 검증을 거침
10. SLA 템플릿·관측성 대시보드·운영 플레이북이 배포 완료되고 경보가 동작함

---

## 12) 참조 구현 스케치

```python
class ConformancePipeline:
    def normalize(self, df, schema, interval_s) -> pd.DataFrame:
        # 1) columns/dtypes normalize
        # 2) tz→UTC, align to [start,end) buckets
        # 3) intra-bucket rollup (OHLCV rules)
        # 4) dedup + flags + lineage cols
        return df

class BackfillCoordinator(Protocol):
    async def claim(self, key:str, lease_ms:int) -> "Lease|None": ...
    async def complete(self, lease:"Lease", ranges:"RangeSet"): ...
    async def fail(self, lease:"Lease", reason:str): ...

class SeamlessDataProvider:
    ...
    async def read(...):
        # coverage→missing
        # small-miss? try sync backfill under SLA; else schedule & PARTIAL
        # merge sources via priority; run through ConformancePipeline
        # build HistoryMeta; return HistoryResult
```

---

## 13) “왜 이게 표준(De facto)에 맞는가”

* **단일 진입점 + 플러그블 소스/전략**: 데이터 레이크/레이크하우스·스트리밍 시스템의 통상 패턴
* **정합성/워터마크/행 품질 플래그**: 스트리밍/배치 혼재 환경(Kappa/Lambda 아키텍처)에서의 업계 관행
* **분산 단일 비행(lease/큐/락)**: 대규모 백필·캐시 워밍에서 일반적으로 요구되는 **idempotent + exactly-once 효과**
* **전략별 SLA/관측성**: SRE 원칙(지연 예산·SLI/SLO)과 잘 맞물리는 운영 모형

---

## 14) 남은 결정 항목

- `SchemaRegistry` 저장소 기술(예: Postgres vs. etcd)과 변경 배포 프로세스(드라이런/승인 단계) 확정
- Backfill Coordinator 백엔드 선택(단일 vs. 다중, Multi-region 지원 필요 여부) 및 장애 시 페일오버 정책 정의
- SLA 템플릿/운영 정책의 소유 조직 확정(데이터 플랫폼 vs. 전략 팀)과 변경 관리 워크플로 마련
- Observability 대시보드와 알림 룰에 대한 유지보수 책임자 및 온콜 로테이션 정리

---

### 부록 A — Issue에 바로 붙일 수 있는 요약(원하면 사용)

**Title:** $RFC$ Seamless v2: 정합성 계층 + 분산 단일 비행 + 전략별 SLA/관측성 통합
**Goals:** 단일 진입점 유지, 정규화 파이프라인, 분산 Coordinator, SLA/타임아웃, 메타데이터, OTel, 테스트/운영 강화
**Key Changes:** HistoryResult(meta), ConformancePipeline, BackfillCoordinator, SLAPolicy, OTel/metrics/logs
**Phased PRs:** SSOT화 → Conformance → Coordinator → SLA/Observability/Tests
**DoD:** §11 참조

---

필요하시면 **SLA 기본 프로파일 값 템플릿**, **Redis/PG 기반 Coordinator 스키마**, **품질 플래그 상수/비트맵 정의**, **Hypothesis 테스트 스켈레톤**을 바로 드리겠습니다.
