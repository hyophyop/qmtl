---
title: "QMTL SR(Strategy Recommendation) 통합 제안서"
tags: [design, integration, sr, strategy-generation, pysr]
author: "QMTL Team"
last_modified: 2025-12-02
status: plan-revised
---

# QMTL SR(Strategy Recommendation) 통합 제안서

!!! warning "Icebox (참고용, 현재 작업 대상 아님)"
    이 문서는 `docs/ko/design/icebox/`에 보관된 참고용 설계 문서입니다. **현재 작업 대상(SSOT)** 이 아니며, 필요 시 배경/아이디어 참고로만 사용하세요. 채택한 내용은 `docs/ko/architecture/` 또는 코드/테스트로 승격해 반영합니다.

## 0. As‑Is / To‑Be 요약

- As‑Is
  - 이 문서는 SR 엔진(PySR/Operon 등)을 QMTL Core Loop(Seamless, Runner.submit, World)와 느슨하게 통합하는 설계를 제안하지만, SR→Runner.submit→WorldService 경로는 일부만 구현되어 있고 auto_returns/World‑level 평가/배분과의 연결은 아직 설계 수준에 머물러 있습니다.
- To‑Be
  - SR 템플릿이 생성하는 전략은 Seamless 데이터, expression_key, validation 샘플, auto_returns 설정 등을 포함해 Runner.submit/WorldService 표준 플로우에 자연스럽게 편입됩니다.
  - 이 문서는 그 연결 지점을 계속 업데이트하되, 상단 As‑Is/To‑Be를 통해 “어디까지 구현되어 있고 무엇이 설계만인지”를 명시적으로 유지합니다.

!!! success "문서 상태: 설계 갱신 (Seamless 단일 경로 우선)"
    - PySR 등 SR 엔진은 **QMTL Seamless Data Provider**를 그대로 사용해 학습/평가합니다.
    - 동일 Seamless Provider로 **warmup→live**까지 이어지게 하여 데이터 불일치 리스크를 차단합니다.
    - `ExpressionDagBuilder → 전략 템플릿 → Runner.submit`로 이어지는 **단일 제출 경로**를 기준으로 SR 통합을 **QMTL 코어와 느슨하게** 결합합니다.
    - DAG Manager 직접 병합/캐싱 경로는 **추후 결정 사항**으로 남기고, 필요 시 `sr_data_consistency_sketch.md`에서 선택합니다.

## 1. 목표

1. **데이터 일관성**: SR 학습/평가/실행이 모두 동일 Seamless Data Provider와 동일 `data_spec`(스냅샷 핸들)을 사용한다.
2. **느슨한 결합**: SR 모듈은 QMTL 코어( World/Gateway/DAG Manager )에 최소한의 의존만 갖는다. 제출은 Runner/World 표준 경로를 사용한다.
3. **즉시 실행 가능**: PySR HOF 수식을 변환기에 넣으면 바로 전략으로 실행되고 World 게이팅을 통과/거부할 수 있다.
4. **중복/정합성 보호**: `expression_key` 기반 dedup과 제출 시 정합성 검증(핸드셰이크)으로 중복 전략과 계산 불일치를 방지한다.

## 2. 핵심 결정

- **Seamless 단일 데이터 경로**: PySR는 QMTL가 제공하는 Seamless Data Provider를 사용해 학습/평가한다. 런타임도 동일 provider를 사용해 warmup/live 전환 시 데이터 불일치를 없앤다.
- **수식→전략 템플릿**: ExpressionDagBuilder(예: `build_expression_dag`)로 Sympy 수식을 DAG 스펙으로 정규화하고, 이를 입력으로 전략 템플릿(예: `build_strategy_from_dag_spec`)을 생성한다. 생성된 Strategy는 Runner/World 제출 표준 경로를 그대로 탄다.
- **필수 메타데이터**:
  - `expression_key` (정규화/해시) — dedup 및 교체 정책용
  - `data_spec` — `dataset_id`, `snapshot_version|as_of`, `partition`, `timeframe` 등 스냅샷 핸들. 스냅샷은 불변이며 교정 시 새 버전을 발급한다.
  - `expression_dag_spec` — 필요 시 Sympy→DAG 변환본 (선택)
  - `sr_engine`, `candidate_id`, `fitness`, `complexity`, `generation`
- **정합성 핸드셰이크(제출 시)**: 제출 페이로드에 validation 샘플을 포함하여 SR 계산 결과와 QMTL 실행 결과를 비교, 불일치 시 거부한다. 기본 허용 오차는 `epsilon`(예: 상대/절대 오차)로 명시한다.
- **World 정책 연계**: World/Gateway가 `expression_key` 기반으로 중복을 거부/교체할 수 있는 정책 플래그를 둔다. 기본은 replace 또는 reject 중 명시적으로 선택하며, 선택 근거를 로그/메트릭으로 남긴다.
- **DAG Manager 직접 병합/캐싱**: Phase 2 선택 사항으로 보류. 필요 시 표현식 서브그래프 재사용·배치 병합을 켠다.

## 3. 범위 / 비범위

- 포함
  - PySR HOF → 수식 → 전략 템플릿 → Runner.submit → World 게이팅 흐름
  - Seamless Data Provider 기반 학습/평가/실행 데이터 일치
  - `expression_key` dedup, 제출 시 정합성 검증(샘플 비교)
  - 기본 메트릭/로그(제출/활성화/중복률)
- 제외(추후 결정)
  - DAG Manager 직접 병합/캐싱/배치 병합
  - SR 오케스트레이션(진화 루프/Population 관리)
  - Gateway 배치 엔드포인트(Phase 2 옵션)

## 4. 단계 계획

### Phase 1 (최소 실행 경로, 권장)
- PySR가 **Seamless Data Provider**로 학습/평가하고 동일 provider를 런타임에 사용.
- ExpressionDagBuilder로 수식/`expression_dag_spec`/`data_spec`을 정규화한 뒤 Strategy 템플릿(`build_strategy_from_dag_spec`)으로 감싸 Runner.submit에 제출.
  - 최소 실행 경로 예시(현재 구현 기준):
    1. PySR HOF → `load_pysr_hof_as_dags(max_nodes=..., data_spec=..., spec_version=...)`.
  2. 각 DAG 스펙을 `build_strategy_from_dag_spec(..., history_provider=SeamlessProvider, sr_engine="pysr")`로 Strategy 생성.
  3. Strategy.metadata에 `expression_key`, `data_spec`, `dedup_policy.expression_key.on_duplicate`, `validation_sample`을 포함해 `Runner.submit`.
  4. World 게이팅 시 expression_key dedup 정책(replace/reject)과 validation 샘플 오차(`epsilon`)를 확인.
- 제출 페이로드(최소): `expression_key`, `spec_version`, `data_spec`, `sr_engine`, `fitness/complexity/generation`, (옵션) `expression_dag_spec`, `validation_sample`.
- WorldPolicy에 `expression_key` 기반 dedup 옵션(replace/reject)을 명시하고, World 로그에 적용 결과를 기록.
- 정합성 핸드셰이크: 제출 시 validation 샘플을 실행해 `epsilon` 허용 오차 내 일치하지 않으면 reject + diff를 반환.

!!! note "제출 메타 포맷 (필수)"
    - `meta.sr`에 포함되는 공통 필드
        - `expression`, `expression_key`, `spec_version`, `data_spec`, `sr_engine`
        - `expression_key_meta.value/spec_version`: 해시 버전 구분용
        - `dedup_policy.expression_key.on_duplicate`: `replace`(기본) 또는 `reject`
    - 예시(JSON):
        ```json
        {
          "meta": {
            "sr": {
              "expression": "x + y",
              "expression_key": "...",
              "spec_version": "v1",
              "data_spec": {"dataset_id": "ohlcv", "snapshot_version": "2025-01-01"},
              "dedup_policy": {
                "expression_key": {
                  "value": "...",
                  "spec_version": "v1",
                  "on_duplicate": "replace"
                }
              }
            }
          }
        }
        ```
    - `expression_key`가 없거나 계산에 실패하면 제출 단계에서 명확한 오류를 반환하고 중복 제어를 건너뛰지 않는다.

### Phase 2 (선택)
- Gateway 배치 제출 API, 검증/정합성의 배치 최적화.
- DAG Manager 직접 병합/캐싱/서브그래프 재사용 스위치 온.
- World/Gateway에서 `expression_key` 그룹별 교체/가중치 재분배 전략 고도화.

### Phase 3 (비권장/장기)
- SR 전용 오케스트레이션/Population 관리는 SR 엔진 책임으로 유지. QMTL에는 도입하지 않음.

## 5. 설계 상세

### 5.1 데이터 경로 (Seamless)
- PySR는 QMTL Seamless Data Provider를 사용하여 학습/평가한다.
- 런타임(백테스트/드라이런/라이브)도 같은 provider를 사용한다.
- `data_spec` 필드 예시: `{dataset_id, snapshot_version|as_of, partition, timeframe, schema(optional)}`.
- 스냅샷 불변성: 같은 snapshot_version/as_of는 수정 금지, 교정 시 새 버전 발급.

### 5.2 수식→전략 템플릿
- 입력: 수식 문자열 또는 Sympy 기반 `expression_dag_spec`, `data_spec`, `sr_engine`, 메타 정보.
- 변환: ExpressionDagBuilder(예: `build_expression_dag`)로 DAG 스펙을 생성/정규화하고, `build_strategy_from_dag_spec`가 Seamless StreamInput/노드를 구성한다.
- 실행: Runner.submit(또는 submit_async)로 World에 제출. World/Gateway는 일반 전략과 동일 파이프라인을 적용.

### 5.3 제출 페이로드 & 정합성 핸드셰이크
- 필드:
  - `expression_key` (정규화 해시, spec_version 포함)
  - `expression_dag_spec` (선택, Sympy→DAG 스펙)
  - `data_spec` (필수, 스냅샷 핸들)
  - `sr_engine`, `candidate_id`, `fitness`, `complexity`, `generation`
  - `validation_sample`: 입력 포인트와 기대 출력 값 + `epsilon`(절대/상대 오차)
- 절차:
  1. Gateway/Runner가 `data_spec`으로 Seamless 데이터를 로드.
  2. 수식(DAG)을 동일 데이터에 실행, `validation_sample`과 비교.
  3. 허용 오차(`epsilon`) 내 일치 시 통과, 불일치면 reject + diff 반환(값, 허용 오차, 스냅샷 ID 포함).

### 5.4 중복/교체 정책
- SR 엔진 측: `expression_key`로 중복 후보 제거/교체.
- World/Gateway: 정책 옵션
  - `expression_key`별 max 1개 활성화
  - `on_duplicate: replace | reject` (default는 환경별로 명시)
  - replace: 동일 expression_key 전략 교체(상태/평가 기록은 정책에 따라 복원/초기화)
  - reject: 기존 전략 유지, 신규 제출은 실패 사유를 명확히 반환
- WorldPolicy 예시(컨셉):
```yaml
selection:
  dedup:
    expression_key:
      enabled: true
      on_duplicate: replace  # 또는 reject
```

### 5.5 관측성
- 제출/활성/중복률/정합성 실패율 메트릭 노출.
- 로그 필수 필드: `expression_key`, `sr_engine`, `candidate_id`, `data_spec`, 실패 유형(스냅샷 미존재/샘플 불일치/정책 거부).

## 6. 구현 체크리스트 (Phase 1)

- [ ] PySR 학습/평가가 Seamless Data Provider를 사용하도록 배선하고, 동일 provider가 Strategy 실행에도 주입됨을 확인.
- [ ] ExpressionDagBuilder → `build_strategy_from_dag_spec` 경로가 Runner.submit 표준 인터페이스와 호환되는지 검증.
- [ ] 제출 페이로드에 `expression_key/spec_version`, `data_spec`, `sr_engine`, `fitness/complexity/generation`, dedup 정책(`on_duplicate`)을 포함.
- [ ] `validation_sample + epsilon` 기반 정합성 핸드셰이크 구현 및 실패 시 명확한 reject 사유/값 diff 반환.
- [ ] WorldPolicy에 `expression_key` dedup 옵션 추가 및 기본값 결정(replace/reject), 적용 결과를 로그/메트릭으로 노출.
- [ ] 메트릭/로그: 제출/활성/중복/정합성 실패율, dedup 정책별 성공/거부 비율 노출.
- [ ] E2E: PySR HOF → 변환기 → Runner.submit → World 게이팅 → 실행까지 active/rejected가 정책/검증 결과와 일치함을 확인.

## 7. 테스트 가이드

- 단위: 표현식 키 정규화, 변환기(수식→전략), data_spec 전달, validation_sample 비교 로직.
- 통합: PySR HOF 샘플 → submit → WorldPolicy dedup 동작, 정합성 실패/성공 케이스.
- 성능(선택): 배치 제출 시 지연/수락률 측정.

## 8. 추후 결정 사항 (Phase 2+)

- Gateway 배치 제출 API와 검증 배치 최적화.
- DAG Manager 직접 병합/캐싱/서브그래프 재사용 스위치.
- World/Gateway에서 표현식 그룹 교체/가중치 재분배 정책 고도화.
- 세부 내용은 `docs/ko/design/icebox/sr_data_consistency_sketch.md`에서 선택/결정.
