# Seamless 데이터 물질화/검증 표면 분리 설계

!!! warning "Icebox (참고용, 현재 작업 대상 아님)"
    이 문서는 `docs/ko/design/icebox/`에 보관된 참고용 설계 스케치입니다. **현재 작업 대상(SSOT)** 이 아니며, 필요 시 배경/아이디어 참고로만 사용하세요. 채택한 내용은 `docs/ko/architecture/` 또는 코드/테스트로 승격해 반영합니다.

!!! warning "Status: draft"
    이 문서는 초안 상태입니다. 구현 과정에서 세부 동작과 API가 변경될 수 있습니다.

## 0. 배경과 문제

- Seamless Data Provider(SDP)는 Core Loop에서 **world 제출 → 평가/활성** 흐름에 붙는 기본 히스토리/라이브 데이터 경로다.
- 한편, “데이터를 미리 채워 두고 검증/아티팩트만 확보”하려는 요구가 있지만, 현 상태에서는 전략 DAG/Runner.submit/WorldService 경로에 얹어야 해 목적이 다른 흐름과 충돌한다.
- 목표: **동일한 SDP 엔진을 유지**하면서도 전략용과 데이터 물질화/검증용 표면을 명시적으로 분리해 책임 경계를 선명하게 만들고, 재현성·안전 가드를 동일하게 적용한다.

## 0-1. 목적/비범위(작업자용 TL;DR)

- 만들 것: **하나의 Seamless 엔진** 위에 얇은 두 표면  
  - 전략 표면: 기존 Runner.submit/WS 경로(변경 없음)  
  - 물질화/검증 표면: SDK 백필 호출을 래핑해 범위 물질화 + conformance/SLA 리포트 + 아티팩트/TTL/priority 처리(WS/activation/allocations 없음)
- 만들지 않을 것(비범위): 새로운 데이터 플레인/스토리지, Runner/WS 변경, 별도 백필 엔진, 일반 ETL 도구
- 구현 방향 한 줄: **“SDK backfill 패턴을 그대로 호출하는 compute-only Job 레이어”**를 추가하고 검증/리포트/보존/경합 정책만 붙인다.

## 1. 설계 원칙

1. **엔진 단일화, 표면 분리**: `SeamlessDataProvider`(컨포먼스·SLA·레지스트리·백필 엔진)는 그대로 두고, 전략용/물질화용 얇은 래퍼를 나눈다.
2. **fail-closed 일관성**: preset `kind/interval` 불일치, 스키마/컨포먼스/SLA 위반은 두 표면 모두에서 즉시 실패한다.
3. **불변 설정**: 인스턴스 생성 시 설정을 고정(immutable)하고, 모드별로 내부 상태/캐시/코디네이터 세션을 섞지 않는다.
4. **재현성 우선**: `dataset_fingerprint`·`as_of`·`coverage_bounds`·컨포먼스/SLA 리포트를 항상 표면으로 노출해 전략/물질화 간 스냅샷 정합성을 보장한다.
5. **경계 명시**: 물질화 표면은 “전략 실행/활성/배분과 무관한 compute-only 경로”임을 문서·API 이름에서 명확히 표현한다.

## 2. 제안 구조

- **공통 엔진**: `qmtl.runtime.sdk.seamless_data_provider.SeamlessDataProvider` (현행)  
  - ConformancePipeline, SLAPolicy, Schema Registry 통합, 분산 백필 코디네이터, artifacts/fingerprint를 그대로 사용.
- **전략 표면 (existing)**: `StrategySeamlessProvider`  
  - world/preset 기반 auto-wiring, live 필수, Runner.submit → WS/activation 경로와 정렬.
- **물질화/검증 표면 (신규)**: `MaterializeSeamlessJob` (또는 유사 클래스)  
  - 입력: preset ID 또는 `SeamlessBuilder` + `start`/`end`(없으면 “as of now”) + 아티팩트/컨포먼스/SLA/retention/priority 옵션.  
  - 동작: `fetch`/`backfill_async`로 범위를 물질화, artifacts/fingerprint를 기록하고 요약 리포트 반환.  
  - 출력: `{dataset_fingerprint, as_of, coverage_bounds, conformance_flags, sla_deadline_ms, retention_class}` 요약(예외 시 fail-closed).  
  - WS/activation/배분 호출 없음, compute-only 보장.  
  - **명시적 모드 플래그**: 생성 시 `mode="strategy"` / `mode="materialize"`로 고정(불변). materialize 모드는 preset에 live가 정의되어 있으면 live 설정 누락 시 실패시키며, live 없는 preset은 storage/backfill만으로 수행한다.
  - **DX 단순화**: 대표 진입점 2–3개(`materialize_and_pin(preset, start, end, retention=...)`, `require_materialized_snapshot(fingerprint=...)`)만 노출해 초기 사용자가 모드 혼동 없이 접근하도록 가이드.

> 선택 사항: 위 Job을 감싼 전용 CLI(`qmtl data materialize …`, `qmtl data verify …`)는 Core Loop CLI와 다른 네임스페이스로 두어 경계를 유지한다.

### 구현 가이드 (SDK 백필 패턴 우선)

- 새로운 백필 엔진/파이프라인을 만들지 않고 **기존 SDK 백필 경로**(`SeamlessDataProvider.fetch` / `backfill_async`, preset + SeamlessBuilder) 위에 Job/헬퍼를 얹는다.  
- Job은 SDK 패턴을 그대로 호출하되, 입력 검증/리포트/아티팩트/TTL/priority 같은 **오케스트레이션 레이어**만 추가한다.  
- Runner.submit/WorldService 경로를 변경하거나 별도 데이터 저장 스택을 추가하지 않는다(단일 엔진 원칙 유지).

### Core Loop 분리·DAG 실행 방식

- **world/submit/WS를 통하지 않는다**: materialize Job은 SDK에서 바로 실행하고, 필요하면 world 파일에서 preset 값만 읽을 뿐 WS/activation/allocations 호출은 없다.  
- **compute-only ExecutionContext**: execution_domain=`compute-only`·mode=`backtest`를 기본으로 해 live 전환을 차단하고, preset에 live가 정의돼 있으면 미제공 시 실패시킨다.  
- **DAG 실행이 필요할 때**: Runner 대신 내부 DAG 실행기로 노드 그래프를 compute-only 컨텍스트에서 돌려 fetch/backfill만 수행한다(라이브 구독·배분 없음).  
- **입력/출력 계약**: 입력은 preset/builder config(+선택적 DAG spec, start/end), 출력은 `{dataset_fingerprint, as_of, coverage_bounds, conformance_flags, sla_violation, attempts, checkpoint_key, retention_class}`.  
- **가드**: live 발견 시 실패, contract_version/fingerprint 불일치 시 실패, artifacts_enabled+artifact_dir(선택적) 검증, priority/TTL는 보고서·정책에 반영.

### 최소 API 스케치 (예시)

```python
class MaterializeReport(TypedDict):
    dataset_fingerprint: str
    as_of: int
    coverage_bounds: tuple[int, int]
    conformance_flags: dict[str, str]
    sla_deadline_ms: int
    retention_class: str

class MaterializeSeamlessJob:
    def __init__(
        self,
        preset: str,
        start: int | None,
        end: int | None,
        *,
        artifact_dir: str | None = None,
        retention_class: str = "research-short",
        priority: str | None = None,
        contract_version: str | None = None,
    ): ...

    async def run(self) -> MaterializeReport: ...
```

필수: preset, (start/end 또는 as_of now), preset에 live가 있으면 live 설정 제공.  
옵션: artifact_dir, retention_class, priority, contract_version(불일치 시 실패), SLA/conformance override는 preset 기준.

## 3. 동작 규약 (전략 vs 물질화)

| 항목 | StrategySeamlessProvider | MaterializeSeamlessJob |
| --- | --- | --- |
| 모드 | live/backtest (WorldService와 정렬) | materialize (compute-only) |
| live 구성 | 필수, preset 불일치 시 실패 | preset에 live가 정의되어 있으면 필수(누락 시 실패), live 없는 preset은 storage/backfill만으로 수행 |
| 범위 | Runner.submit가 결정(월드·리플레이 창) | `start/end` 또는 `as_of now` |
| 출력 | WS/activation/allocations + Seamless 메타 | fingerprint/as_of/coverage + conformance/SLA 요약 |
| 검증 | preset kind/interval·레지스트리·컨포먼스·SLA | 동일한 검증을 그대로 적용 (fail-closed) |
| 아티팩트 | 선택(`artifacts_enabled`) | 기본 on 권장, `artifact_dir` 필수화 가능 |

## 4. 재사용 가이드 (충돌 방지)

- **동일 preset/SeamlessConfig**를 사용하면 물질화에 쓴 데이터 스냅샷을 전략에서도 그대로 재사용 가능.  
- materialize 결과에 포함된 `dataset_fingerprint/as_of/coverage_bounds`를 전략 실행 전 고정해 재현성 확보.  
- **데이터 계약 버전**: preset에 `contract_version`(또는 동등 키)을 두고 Materialize/Strategy 양쪽이 동일 버전을 사용하지 않으면 실패하도록 옵션화(`require_contract_version(v)`, `require_fingerprint(f)` 같은 체크포인트 헬퍼 고려).  
- 라이브가 얽힌 preset은 시점/`stabilization_bars` 차이만 주의하면 무리 없이 공유 가능.

## 5. 관측·안전 가드

- 메트릭/로그: `seamless_sla_deadline_seconds`, `backfill_completion_ratio`, `seamless_conformance_flag_total` 기본 활성.  
- 리포트: materialize 표면은 conformance/SLA 요약 JSON을 기본 반환하고, 실패 시 `ConformancePipelineError` / `SeamlessSLAExceeded`를 그대로 노출.  
- 레이트리밋/코스트: 대량 백필 시 쿼터/레이트리밋 설정을 명시적으로 요구하고, 로그에 경고 포함. materialize 경로에는 `priority`/`rate_limit_profile` 옵션을 두어 전략 실행과 경합 시 기본적으로 materialize가 양보하게 설정.  
- 보존/TTL: `retention_class`(예: `regulatory-long`, `research-short`)와 TTL 입력을 받아 아티팩트/스토리지 보관 기간을 정책적으로 관리하고, 만료 시 GC 또는 저비용 스토리지로 이동.  
- Job 수명주기: Materialize Job은 idempotent 키(예: preset+start/end+contract_version) 기반 체크포인트를 기록해 부분 실패 시 재개(resume) 가능해야 한다. 재시도/중복 실행 시 덮어쓰기 vs 새 스냅샷 생성 정책을 로그/리포트에 명시한다.

## 6. 테스트 전략

- 공통 계약: preset 불일치·스키마/컨포먼스/SLA 위반 시 양쪽 표면 모두 fail-closed 되는지 검증.  
- 모드별 계약:  
  - 전략 표면: live 누락 시 실패, WS/activation 경로와 정렬된 출력.  
  - 물질화 표면: `start/end` 범위 물질화 후 fingerprint/as_of/coverage 리포트 반환, preset에 live가 있으면 live 누락 시 실패, live 없는 preset은 storage/backfill만으로 성공.  
- 실패/복구 시나리오: 네트워크 중단·partial 물질화 후 resume, schema evolution(새 `contract_version`) 시 실패/경고 처리, rate-limit 초과 시 백오프 정책을 계약 테스트로 고정.  
- E2E 예시: core-loop demo preset으로 materialize → fingerprint/coverage 확인 → 동일 preset/contract_version으로 Runner.submit 실행 시 동일 스냅샷 소비 확인.

### 테스트 케이스 체크리스트

- 계약 위반: preset interval/kind 불일치 → 즉시 실패.  
- live 필수 preset에서 live 누락 → 실패. live 없는 preset은 성공.  
- contract_version 불일치 → 실패. fingerprint mismatch → 실패.  
- SLA/컨포먼스 위반 → 예외 전파, 리포트에 flag 기록.  
- resume: 중간 실패 후 동일 key로 재시도 시 덮어쓰기/재개 동작 확인.  
- rate-limit 초과 → 백오프/경고 동작.  
- retention_class/TTL 설정 시 만료 후 GC 또는 보관 이동 로그 확인.  
- E2E: materialize → Runner.submit 동일 preset/contract_version 소비 시 동일 coverage/fingerprint.

## 7. 롤아웃 메모

- 코드 변경 범위는 SDK 층에 국한(엔진 재사용), Core Loop CLI/WS 경로는 변경하지 않는다.  
- 문서: 본 설계를 `../../architecture/seamless_data_provider_v2.md`와 가이드에 링크하고, “데이터 물질화/검증 전용” 섹션을 추가해 범위·경계를 명시.  
- CLI 추가 시 별도 네임스페이스를 사용해 Runner.submit 흐름과 UI 충돌을 방지한다.  
- 도입 절차: feature flag로 shadow 모드 → 팀/preset 단위 opt-in → 문제 없을 때 일반 공개. 롤백 시 flag로 즉시 차단. `qmtl --help`에서 data 네임스페이스와 core-loop 네임스페이스를 명확히 분리해 혼동을 줄인다.

## 8. 구현 시 DoD/체크리스트

- API: `MaterializeSeamlessJob`/`MaterializeReport` 시그니처, 필수/옵션 인자 표기.  
- 검증: preset kind/interval, live 필수 여부, contract_version/fingerprint 일치, SLA/컨포먼스 fail-closed.  
- 리포트: `dataset_fingerprint`, `as_of`, `coverage_bounds`, `conformance_flags`, `sla_deadline_ms`, `retention_class` 필수.  
- 보존/우선순위: `retention_class` → TTL/보관 정책, `priority`/`rate_limit_profile` 적용.  
- 아티팩트: artifacts_enabled 적용 시 artifact_dir 필수, 기록 경로 로그.  
- 관측: 메트릭/로그(coverage, conformance_flags, SLA, resume/attempts) 방출.  
- 테스트: 위 테스트 체크리스트 항목 구현.

## 9. 워크플로 예시 (요약)

1) `MaterializeSeamlessJob(preset="ohlcv.binance.spot.1m", start=..., end=..., contract_version="v1")` 생성 → `run()`  
2) 리포트에서 `dataset_fingerprint/as_of/coverage_bounds` 확인, artifacts 확인(필요 시)  
3) 동일 preset/contract_version으로 `Runner.submit(..., world=..., ...)` 실행 → WS/activation 출력에서 Seamless 메타(coverage/fingerprint) 일치 확인  
4) 만료 정책(retention_class)에 따라 아티팩트/스토리지 GC 또는 보관 이동

## 8. 참고 문서

- [Seamless Data Provider v2 아키텍처](../../architecture/seamless_data_provider_v2.md)  
- [Seamless Data Provider 아키텍처](../../architecture/seamless_data_provider_v2.md)  
- 관련: [architecture/seamless_data_provider_v2.md](../../architecture/seamless_data_provider_v2.md), [architecture/architecture.md Core Loop 요약](../../architecture/architecture.md#core-loop-summary)

---

## 9. Claude Opus 4.5 의견 (2025-12-06)

### 장점

1. **명확한 책임 분리 (SoC 준수)**
   - 전략 실행 경로(`StrategySeamlessProvider`)와 데이터 물질화 경로(`MaterializeSeamlessJob`)를 명시적으로 분리
   - 각 표면(surface)이 서로 다른 목적을 가지며, 상호 간섭 없이 독립적으로 동작
   - CLI 네임스페이스 분리로 UI/UX 혼란 방지

2. **엔진 재사용으로 인한 일관성 확보**
   - `SeamlessDataProvider` 엔진을 공유하여 ConformancePipeline, SLA, Schema Registry 등 핵심 로직 중복 제거
   - 두 표면 모두 동일한 검증 파이프라인을 거치므로 fail-closed 동작이 일관됨
   - 코드 변경 범위가 SDK 층에 국한되어 Core Loop 영향 최소화

3. **재현성 우선 설계**
   - `dataset_fingerprint`, `as_of`, `coverage_bounds`를 항상 노출하여 스냅샷 정합성 보장
   - 물질화된 데이터를 전략에서 그대로 재사용 가능 → 테스트/백테스트 재현성 확보

4. **관측성 (Observability) 내장**
   - 메트릭(`seamless_sla_deadline_seconds`, `backfill_completion_ratio` 등) 기본 활성화
   - Conformance/SLA 요약 JSON 반환으로 디버깅 및 감사 추적 용이

5. **안전 가드**
   - preset `kind/interval` 불일치, 스키마/SLA 위반 시 즉시 실패 (fail-closed)
   - 불변 설정(immutable config)으로 런타임 상태 혼합 방지
   - 대량 백필 시 레이트리밋/쿼터 명시 요구

### 단점 및 개선 고려사항

1. **추상화 레이어 증가**
   - 기존 `SeamlessDataProvider` 위에 `StrategySeamlessProvider`, `MaterializeSeamlessJob` 래퍼가 추가됨
   - 래퍼가 "thin"하다고 명시했지만, 시간이 지나면 로직이 누적되어 leaky abstraction 위험
   - **제안**: 래퍼의 책임 범위를 엄격히 문서화하고, 정기적으로 코드 복잡도(radon CC) 모니터링

2. **두 표면 간 설정 동기화 부담**
   - 동일 preset을 공유하더라도 `stabilization_bars`, live 설정 등에서 미묘한 차이 발생 가능
   - 물질화 시점과 전략 실행 시점의 `as_of` 불일치로 인한 silent data drift 위험
   - **제안**: preset-level fingerprint validation을 전략 실행 전 필수 체크포인트로 만들거나, `MaterializeSeamlessJob` 결과를 전략에 주입하는 명시적 API 제공

3. **Dry-live 모드의 모호성 (해결됨)**
   - 과거에는 물질화 표면에서 "live 미사용 가능(dry-live)"을 논의했으나, 현재 설계에서는 옵션을 제거하고 live가 정의된 preset에서는 live 누락 시 실패하도록 정리됨.
   - live 없이도 되는 preset은 storage/backfill만으로 수행하도록 명시해 환경 불일치를 방지.

4. **CLI 네임스페이스 분리의 일관성 미검증**
   - `qmtl data materialize`, `qmtl data verify` 등 CLI 추가를 "선택 사항"으로 두었으나, 실제 구현 시 기존 CLI와의 충돌/일관성 검토 필요
   - **제안**: CLI 설계를 선택이 아닌 필수로 올리고, `qmtl --help` 출력에서 명확한 카테고리 분리 확인

5. **테스트 전략의 구체성 부족**
   - E2E 예시가 한 줄로 요약되어 있으나, 실제 테스트 케이스(edge case) 정의 부재
     - 예: 물질화 중 네트워크 실패 시 재시도 동작
     - 예: 부분 물질화 후 전략 실행 시 coverage gap 처리
   - **제안**: 실패 시나리오(partial failure, timeout, schema evolution)에 대한 계약 테스트 추가

6. **롤아웃 리스크 평가 부재**
   - "코드 변경 범위는 SDK 층에 국한"이라고 했으나, 기존 `StrategySeamlessProvider` 사용처에 대한 backward compatibility 검증 계획 없음
   - **제안**: 단계적 롤아웃 계획 (feature flag, shadow mode) 및 롤백 절차 명시

### 종합 평가

| 구분 | 평가 |
|------|------|
| 아키텍처 원칙 준수 | ✅ SoC, DRY, fail-closed 원칙 잘 준수 |
| 재현성/관측성 | ✅ fingerprint, 메트릭, 리포트로 충분히 지원 |
| 구현 복잡도 | ⚠️ 래퍼 레이어 추가로 인한 유지보수 부담 가능 |
| 설정 동기화 | ⚠️ 두 표면 간 미묘한 drift 위험 존재 |
| 테스트 명세 | ⚠️ edge case 및 실패 시나리오 보완 필요 |
| 롤아웃 계획 | ⚠️ backward compatibility 및 롤백 절차 명시 필요 |

> 전반적으로 설계 원칙은 견고하나, 운영 안전성(drift 방지, 롤아웃 계획, 실패 시나리오 테스트)에 대한 세부 명세 보완이 필요함.

---

## 10. Gemini 3 Pro 의견 (2025-12-06)

### 장점

1. **운영 효율성 및 워크플로우 최적화**
   - 물질화(Materialize) 단계를 명시적으로 분리함으로써, 대규모 백테스트 전 '사전 물질화(Pre-materialization)' 패턴을 공식화할 수 있음.
   - 전략 실행 시 데이터 로딩/검증 오버헤드를 제거하여 반복적인 실험 속도를 획기적으로 높일 수 있음.

2. **데이터 거버넌스 및 감사 추적(Audit Trail)**
   - `dataset_fingerprint`와 `conformance_flags`를 리포트 형태로 남기는 것은 금융 규제 준수나 내부 감사에 매우 유리함.
   - 어떤 데이터 스냅샷으로 전략이 의사결정을 내렸는지 역추적(Lineage)이 가능해짐.

3. **컴퓨팅 리소스 분리 및 확장성**
   - `MaterializeSeamlessJob`은 순수 계산(compute-only) 작업이므로, 향후 Ray, Spark 등의 분산 처리 시스템이나 AWS Lambda 같은 서버리스 환경으로 오프로딩하기 매우 적합한 구조임.
   - 전략 서버와 데이터 처리 서버의 리소스 스케일링을 독립적으로 가져갈 수 있음.

### 단점 및 개선 고려사항

1. **실패 복구 및 재개(Resume) 전략 부재**
   - 대용량 데이터 물질화 중 실패했을 때, 처음부터 다시 시작해야 하는지 아니면 체크포인트부터 재개할 수 있는지에 대한 명세가 부족함.
   - **제안**: Job 상태 관리(State Management) 및 체크포인팅 메커니즘을 설계에 포함해야 함.

2. **리소스 경합 및 우선순위 제어**
   - 전략 실행(Live/Backtest)과 물질화 작업이 동일한 데이터 소스나 네트워크 대역폭을 공유할 때의 우선순위 처리(Throttling) 방안이 없음.
   - **제안**: `MaterializeSeamlessJob`에 `priority` 옵션을 추가하거나, 시스템 부하 시 백필 속도를 조절하는 메커니즘 고려.

3. **스토리지 라이프사이클 관리(TTL)**
   - 물질화된 아티팩트가 계속 쌓일 경우 스토리지 비용 문제 발생 가능.
   - **제안**: 아티팩트의 유효 기간(TTL) 설정이나 오래된 데이터 자동 정리(GC) 정책을 설계에 포함해야 함.

4. **개발자 경험(DX) 및 인지 부하**
   - 사용자가 언제 `StrategySeamlessProvider`를 쓰고 언제 `MaterializeSeamlessJob`을 써야 하는지 혼동할 수 있음.
   - **제안**: 명확한 가이드 문서와 함께, 사용 목적에 따라 적절한 구현체를 선택해주는 팩토리 패턴이나 고수준 API 제공 고려.

### 종합 평가

| 구분 | 평가 |
|------|------|
| **확장성/최적화** | ✅ 분산 처리 및 사전 물질화 워크플로우에 최적화된 구조 |
| **거버넌스** | ✅ Audit Trail 및 Lineage 추적 용이 |
| **운영 디테일** | ⚠️ 재개(Resume), TTL, 리소스 격리 등 운영 정책 보완 필요 |
| **DX** | ⚠️ 두 표면의 사용 가이드 및 추상화 보완 필요 |

> 데이터 엔지니어링(물질화)과 퀀트 리서치(전략)의 경계를 나누는 합리적인 설계이나, 실제 운영 환경에서의 리소스 관리와 비용 효율성에 대한 고려가 추가되어야 함.


11. GPT-5.1 Pro 의견 (2025-12-06)
장점


“엔진 단일화 + 표면 분리”라는 구조적 선택의 적합성


동일한 SeamlessDataProvider 엔진 위에 전략 표면(StrategySeamlessProvider)과 물질화/검증 표면(MaterializeSeamlessJob)을 올리는 구조는, 운영·거버넌스 관점에서 보면 “데이터 계약(data contract)은 하나, 소비자용 인터페이스는 여러 개”라는 현대 데이터 플랫폼 패턴과 잘 맞음.


이로 인해 스키마/컨포먼스/SLA 관련 정책을 한 번 정의하면 두 경로에 일관되게 적용할 수 있고, 규제 환경(퀀트/금융 도메인)에서 요구되는 통제 강도를 유지하기 용이함.




전략/데이터 팀 간 역할 분리와 협업 구조에 유리


전략 실행(Core Loop)과 데이터 물질화/검증을 분리된 표면으로 제공함으로써, “전략 팀은 preset을 소비하고, 데이터 팀은 동일 preset을 기준으로 물질화 파이프라인을 관리”하는 책임 분리가 자연스럽게 만들어짐.


특히 dataset_fingerprint, as_of, coverage_bounds를 물질화 결과로 명시적으로 넘겨주도록 한 설계는, 팀 간 인터페이스를 “숫자/시간/범위 기반 계약”으로 고정하는 효과가 있어 조직 규모가 커질수록 장점이 커짐.




재현성과 규제 대응력 측면에서의 설계 성숙도


전략/물질화 경로 모두에서 fail-closed, fingerprint 기반 재현성, conformance/SLA 리포트를 강조하고 있어, “어떤 데이터 스냅샷에서 어떤 전략이 어떤 의사결정을 내렸는가”를 시간 뒤에 복원할 수 있는 기반이 잘 마련됨.


이는 백테스트 검증, 컴플라이언스 리뷰, 외부 감사 등 고신뢰 요구사항에 대응하기 좋은 구조로, 단순한 리서치 툴을 넘어 “프로덕션-grade 리서치 플랫폼”을 지향하는 방향성과 일치함.




compute-only 물질화 경로의 성능·확장성 잠재력


MaterializeSeamlessJob을 world/activation/allocations와 완전히 분리된 compute-only 경로로 정의한 것은, 향후 분산 백필·서버리스 실행·워크로드 오케스트레이션(Airflow/Argo 등)과의 통합에 유리한 선택임.


전략 서버와 물질화/백필 서버의 리소스를 분리 스케일링 할 수 있어, “실험 속도 vs 운영 안정성” 간 트레이드오프를 정책으로 조정하기 쉬움.




관측성과 운영 통제장치에 대한 감각


SLA/컨포먼스·백필 진행률 메트릭, fail-closed 예외, 레이트리밋/쿼터 요구 등 운영 측면의 요소가 설계 단계에서부터 고려되어 있어, 단순 라이브러리가 아닌 “운영 가능한 시스템 컴포넌트”로 보는 접근이 돋보임.


이는 향후 SRE/플랫폼팀 관점에서도 수용성이 높은 구조가 될 가능성이 크다.




단점 및 개선 제안


“두 개의 표면”이 아니라 “두 개의 모드”로 인지될 위험


개념적으로는 표면이 분리되어 있으나, 실제 사용하는 입장에서는 “Strategy 모드 vs Materialize 모드” 정도로만 이해하고 혼용할 수 있음.


특히 preset 재사용을 강조하고 있어, 잘못된 가이드/샘플 코드가 나가면 Materialize 경로를 사실상 “큰 백테스트 한 번 돌리기” 용도로만 쓰는 등 오·남용 가능성이 존재.


제안:


문서와 API 이름에서 “materialize = data plane, strategy = decision/alpha plane” 관점을 더 강하게 드러내고,


샘플 코드/튜토리얼에서 두 표면을 섞어 쓰는 패턴을 의도적으로 제한하는 것이 좋음.






preset·fingerprint·schema 버전 간 관계 명세 부족


현 설계는 dataset_fingerprint, as_of, coverage_bounds를 노출한다고 되어 있으나, 다음과 같은 질문에 대한 명확한 계약이 아직 부족하다:


schema 변경(컬럼 추가/타입 변경)이 발생했을 때 fingerprint 버전은 어떻게 달라지는지?


동일 preset 이름을 쓰더라도, schema/conformance 정책이 바뀐 경우를 어떻게 구분할지?


전략 실행 시 “어떤 fingerprint 범위까지 허용할 것인지”를 선언적으로 제한할 수 있는지?




제안:


preset에 “data contract version” 개념을 추가하여, Materialize/Strategy 양쪽에서 동일 버전을 사용하지 않을 경우 fail-closed 되도록 하는 옵션을 고려.


fingerprint 비교를 위한 API(require_fingerprint(f), require_contract_version(v) 등)를 Strategy 표면에 추가해, 전략 코드 레벨에서 재현성 정책을 명시할 수 있게 하는 것이 바람직함.






Job 수명주기 및 상태 관리 설계의 부재


MaterializeSeamlessJob이라는 이름은 “Job” 개념을 암시하지만, 문서에는 다음과 같은 운영 시나리오에 대한 명세가 부족하다:


대량 물질화 중 일부 구간 실패 시 재실행/재개 전략(체크포인팅, idempotency, partial success 처리)


동일 Job을 여러 번 실행했을 때의 의미(덮어쓰기 vs 새로운 스냅샷 생성)


Job 메타데이터(요청자, 목적, 우선순위, TTL 등)를 어디서 관리할지




제안:


“Job Registry” 또는 “Run History” 레벨의 개념을 별도 문서/컴포넌트로 도입해, Materialize 작업을 단순 함수 호출이 아닌 추적 가능한 엔티티로 모델링하는 것을 고려.


최소한 TTL, 재시도 정책, priority(전략 vs 백필 경합 시) 정도는 Job-level 옵션으로 표준화하는 것이 좋음.






스토리지/비용 관점에서의 정책 부족


아티팩트 및 물질화된 데이터가 기본적으로 “계속 남는다”는 가정이라면, 장기적으로 스토리지 비용과 관리 복잡도가 급격히 증가할 수 있음.


특히 규제 대응을 이유로 모든 스냅샷을 무기한 보관하는 패턴이 생기면, 인프라/비용 측면의 리스크가 현실화될 가능성이 큼.


제안:


“규제 대응용 스냅샷(긴 TTL)”과 “리서치용 스냅샷(짧은 TTL)”을 구분하는 정책 레이어를 도입.


Materialize 결과에 TTL/retention-class를 명시하고, 백엔드에서 자동 GC 또는 아카이빙(저비용 스토리지로 이동) 정책을 붙이는 것이 바람직함.






DX(Developer Experience)와 온보딩 비용


StrategySeamlessProvider / MaterializeSeamlessJob / SeamlessDataProvider / preset / SeamlessBuilder 등 개념이 많아, 신규 사용자(특히 데이터 엔지니어가 아닌 퀀트 리서처)에겐 진입장벽이 될 수 있음.


제안:


“가장 흔한 사용 패턴”에 대해 opinionated high-level API를 제공하는 것을 고려


예: qmtl.data.materialize_and_pin(preset, start, end)


예: strategy.require_materialized_snapshot(snapshot_id)




내부적으로는 현재 설계를 유지하되, 외부에는 2~3개의 대표적인 고수준 진입점을 노출해 인지 부하를 줄이는 방향이 이상적임.






롤아웃·호환성 전략의 구체화 필요


설계 상으로는 SDK 레이어에만 변경이 국한된다고 하나, 실제로는 기존 호출자들이 새로운 표면/옵션을 혼합 사용하면서 예상치 못한 동작을 만들 수 있음.


제안:


feature flag를 두고, 초기에는 Materialize 표면을 “shadow mode”로만 운영하면서 메트릭과 실패 패턴을 관찰.


기존 Strategy 경로에서 “materialize를 거친 snapshot만 허용”하는 강모드로 한 번에 전환하기보다는, 팀/preset 단위로 점진적으로 강제하는 롤아웃 플랜을 별도 문서로 정의하는 것이 안정적임.






종합 평가


이 설계는 데이터 계약과 엔진을 단일화하면서, 전략 실행과 데이터 물질화/검증을 명확히 분리하려는 의도가 잘 드러나 있으며, 재현성·관측성·거버넌스 측면에서 현대적인 기준을 상당 부분 충족하고 있다.


반면 실제 운영 환경에서 중요한 job 수명주기 관리, preset/contract 버전 관리, 스토리지/비용 정책, DX/온보딩, 단계적 롤아웃 전략 등은 아직 추상 수준에 머물러 있고, 후속 설계/문서화가 필요하다.


요약하면, “엔진과 표면”의 아키텍처 방향성은 타당하며 큰 수정 없이도 채택 가능해 보이지만, 운영·조직·비용 차원의 세부 정책 레이어를 위 설계 위에 얹는 작업이 완료되어야 “프로덕션 도입 준비가 된 설계”로 평가될 수 있을 것이다.
