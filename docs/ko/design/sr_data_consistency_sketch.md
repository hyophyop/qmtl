---
title: "SR-QMTL 데이터 일관성 설계 스케치"
tags: [design, draft, sr, data-consistency]
author: "QMTL Team"
last_modified: 2025-11-27
status: sketch
related: sr_integration_proposal.md
---

# SR-QMTL 데이터 일관성 설계 스케치

!!! warning "임시 문서"
    이 문서는 논의용 스케치입니다. 결정 후 `sr_integration_proposal.md`에 통합 예정.

## 1. 문제 정의

SR 엔진(Operon)에서 수식을 평가할 때 사용한 데이터와 QMTL에서 같은 수식을 DAG로 실행할 때 사용하는 데이터가 일치해야 합니다.

```
┌─────────────────────────────────────────────────────────────────┐
│                    SR 엔진 (피트니스 평가)                       │
│                                                                  │
│   데이터 A  +  수식 F  →  신호 S₁  →  피트니스 계산               │
│   (어떤 데이터?)                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 전략 제출 (수식 F만 전달)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         QMTL (실행)                              │
│                                                                  │
│   데이터 B  +  수식 F  →  신호 S₂  →  실제 매매                   │
│   (QMTL이 가진 데이터)                                          │
└─────────────────────────────────────────────────────────────────┘

문제: S₁ ≠ S₂ 이면 SR에서 좋았던 전략이 실제로는 다르게 동작
```

### 1.1 데이터 불일치 원인

| 원인 | 설명 | 영향도 |
|------|------|--------|
| **시점 불일치** | SR 평가 시점 vs QMTL 실행 시점의 데이터 범위/최신성 | 높음 |
| **소스 불일치** | SR이 사용하는 데이터 소스 vs QMTL 데이터 소스 (거래소, 벤더) | 높음 |
| **전처리 불일치** | 결측치 처리, 정규화, 리샘플링 방식 | 중간 |
| **심볼/유니버스 불일치** | SR이 평가한 심볼셋 vs QMTL이 사용하는 심볼셋 | 높음 |

---

## 2. 방안 비교

### 방안 1: QMTL을 Single Source of Truth로

```
┌─────────────────────────────────────────────────────────────────┐
│                    QMTL (데이터 마스터)                          │
│                                                                  │
│   DataProvider API  ───────────────────────────────────────────  │
│   - /data/fetch?symbols=...&start=...&end=...                   │
│   - /data/snapshot?universe_id=...                              │
└─────────────────────────────────────────────────────────────────┘
          │                           │
          │ (동일 API 호출)            │ (동일 데이터 사용)
          ▼                           ▼
┌─────────────────────┐     ┌─────────────────────────────────────┐
│    SR 엔진          │     │    QMTL 실행                        │
│    피트니스 평가    │     │    DAG 실행 (전략 운용)             │
└─────────────────────┘     └─────────────────────────────────────┘
```

**장점:**
- 데이터 일관성 보장
- QMTL이 데이터 계보(lineage) 관리

**단점:**
- SR 엔진이 QMTL 의존
- SR 평가 성능 병목 가능

**평가:** ⭐⭐⭐

---

### 방안 2: 데이터 스펙 기반 검증

```
┌─────────────────────────────────────────────────────────────────┐
│                    SR 전략 메타데이터                            │
│                                                                  │
│   data_spec:                                                     │
│     source: "binance"                                            │
│     symbols: ["BTC/USDT", "ETH/USDT"]                           │
│     timeframe: "1h"                                              │
│     train_start: "2024-01-01"                                   │
│     train_end: "2024-06-30"                                     │
│     data_hash: "sha256:abc123..."  # 실제 사용 데이터 해시      │
└─────────────────────────────────────────────────────────────────┘
          │
          │ 제출 시 검증
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    QMTL 검증                                     │
│                                                                  │
│   1. data_spec 호환성 확인 (source, timeframe 지원 여부)        │
│   2. 데이터 가용성 확인 (symbols이 universe에 있는지)           │
│   3. [선택적] data_hash 재현 가능 여부 확인                     │
└─────────────────────────────────────────────────────────────────┘
```

**장점:**
- SR 엔진 독립성 유지
- 메타데이터로 검증

**단점:**
- 사후 검증
- 미스매치 시 전략 reject만 가능

**평가:** ⭐⭐

---

### 방안 3: 공유 데이터 레이어 (Feature Store)

```
┌─────────────────────────────────────────────────────────────────┐
│              Shared Data Layer (Feature Store)                   │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Universe Registry                                       │   │
│   │  - universe_id: "crypto_major_v1"                       │   │
│   │  - symbols, source, timeframe 정의                      │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Materialized Features (QMTL DAG 결과)                  │   │
│   │  - close, volume, EMA_20, RSI_14, ...                   │   │
│   │  - 버전 관리 (snapshot_id, timestamp)                   │   │
│   └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
          │                           │
          │ (읽기 전용)               │ (읽기/쓰기)
          ▼                           ▼
┌─────────────────────┐     ┌─────────────────────────────────────┐
│    SR 엔진          │     │    QMTL                             │
│                     │     │                                      │
│  - universe_id 참조 │     │  - Feature 생성/관리                │
│  - Feature 읽기     │     │  - Universe 관리                    │
│  - 피트니스 평가    │     │  - 전략 실행                        │
└─────────────────────┘     └─────────────────────────────────────┘
```

**장점:**
- 데이터 일관성 보장
- SR 엔진이 이미 계산된 Feature 재사용 (성능 이점)
- Universe 기반 데이터 범위 명확화

**단점:**
- 공유 스토리지 인프라 필요
- SR 엔진이 QMTL Feature 포맷에 맞춰야 함

**평가:** ⭐⭐⭐⭐ (권장)

---

## 3. 비교 요약

| 항목 | 방안 1 (QMTL SSOT) | 방안 2 (스펙 검증) | 방안 3 (Feature Store) |
|------|-------------------|-------------------|----------------------|
| 데이터 일관성 보장 | ✅ 완전 | ⚠️ 사후 검증 | ✅ 완전 |
| SR 엔진 독립성 | ❌ QMTL 의존 | ✅ 독립 | ⚠️ 포맷 의존 |
| 성능 | ⚠️ API 병목 | ✅ 영향 없음 | ✅ Feature 재사용 |
| 인프라 복잡도 | 중간 | 낮음 | 높음 |
| 구현 난이도 | 중간 | 낮음 | 높음 |

---

## 4. 권장안: 방안 3 + 방안 2 혼합

### 4.1 기본 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                    Feature Store (공유 레이어)                   │
│                                                                  │
│   Universe: "crypto_major_v1"                                   │
│   ├── raw: close, open, high, low, volume                       │
│   └── derived: EMA_20, RSI_14, MACD, ... (QMTL DAG 결과)       │
└─────────────────────────────────────────────────────────────────┘
          │
          ├─────────────────────────────────────────────┐
          │                                              │
          ▼                                              ▼
┌─────────────────────┐                      ┌──────────────────────┐
│    SR 엔진          │                      │    QMTL              │
│                     │                      │                      │
│  DataContext:       │                      │  DataContext:        │
│    universe_id      │  ─── 일치 확인 ───   │    universe_id       │
│    snapshot_id      │                      │    snapshot_id       │
│    feature_set      │                      │    feature_set       │
└─────────────────────┘                      └──────────────────────┘
```

### 4.2 DataContext 계약

```python
@dataclass
class DataContext:
    """SR-QMTL 간 데이터 일관성을 보장하는 컨텍스트
    
    주의: (universe_id, snapshot_id) 조합은 논리적으로 불변(immutable)인 데이터 스냅샷을 가리켜야 한다.
    """
    
    universe_id: str          # "crypto_major_v1"
    snapshot_id: str          # "2024-06-30T00:00:00Z" 또는 해시
    feature_set: list[str]    # ["close", "volume", "EMA_20", ...]
    
    # 메타데이터 (검증용)
    source: str               # "binance"
    timeframe: str            # "1h"
    symbols: list[str]        # ["BTC/USDT", "ETH/USDT"]
    
    # 선택적: 데이터 무결성 해시
    data_hash: str | None = None
    context_version: str = "v1"   # DataContext 스키마/해석 규칙 버전
```

### 4.3 워크플로우

```
1. [QMTL] Universe 정의 및 Feature 사전 계산
   - universe_id: "crypto_major_v1" 생성
   - DAG 실행하여 기본 Feature 계산 (close, EMA_20, RSI_14, ...)
   - Feature Store에 저장

2. [SR 엔진] Feature Store에서 데이터 로드
   - DataContext(universe_id="crypto_major_v1", snapshot_id="...") 생성
   - Feature 읽기: close, volume, EMA_20, ...
   - 진화/피트니스 평가 수행

3. [SR 엔진] 전략 제출
   - SRCandidate에 DataContext 포함:
     candidate.data_context = DataContext(
         universe_id="crypto_major_v1",
         snapshot_id="2024-06-30T00:00:00Z",
         ...
     )

4. [QMTL] 제출 시 검증
   - DataContext.universe_id가 활성 universe인지 확인
   - snapshot_id가 유효한지 확인
   - 필요한 feature_set이 모두 있는지 확인

5. [QMTL] 전략 실행
   - 동일한 universe_id/snapshot_id 기반으로 DAG 실행
   - 데이터 일관성 보장됨
```

---

## 5. 미결정 사항

- [ ] Feature Store 구현체 선정 (Redis, PostgreSQL, Parquet, ...)
- [ ] snapshot_id 관리 정책 (시간 기반 vs 해시 기반)
- [ ] Feature 버전 관리 방식
- [ ] SR 엔진이 새 Feature를 요청할 수 있는지 (read-only vs read-write)

---

## 6. 용어 정리 및 operon 설계와의 관계

### 6.1 DataContext와 data_spec/data_context 매핑

- 이 문서에서 정의한 `DataContext`는 SR-QMTL 간 **데이터 컨텍스트의 정규화된 개념 모델**입니다.
  - 핵심 필드: `universe_id`, `snapshot_id`, `feature_set`
  - 보조 메타데이터: `source`, `timeframe`, `symbols`, `data_hash`
- `docs/ko/design/sr_integration_proposal.md`에서는 동일 계열의 개념을 다음 용어로 사용합니다.
  - `data_spec`: `DataContext`를 직렬화했을 때의 최소 서브셋 (현재는 주로 스냅샷 핸들 역할)
  - `data_context`: 제출 핸드셰이크에서 사용하는, 스냅샷 식별에 필요한 필드 묶음
- 정렬 기준:
  - `DataContext` ⊇ `data_context` ⊇ `data_spec`  
    (operon 설계는 `DataContext`의 부분 집합만을 현재 요구하며, 필요 시 필드를 확장할 수 있습니다.)

!!! important "불변 스냅샷과 DataContext 버전 관리"
    - `(universe_id, snapshot_id)` 조합은 언제나 **불변 스냅샷**을 가리키며, 사후 덮어쓰지 않는 것을 원칙으로 합니다.  
    - `context_version`은 DataContext 스키마/해석 규칙의 버전을 나타내며,  
      향후 Feature Store 구조나 필드 구성이 변경되더라도 버전별로 의미를 구분할 수 있도록 합니다.

### 6.2 Feature Store의 위치

- 본 문서의 권장안(방안 3 + 방안 2 혼합)은 `DataContext`를 **공유 Feature Store 위에 올리는 구조**를 상정합니다.
  - Universe Registry + Materialized Features를 기반으로 universe/snapshot/feature_set를 관리.
  - SR 엔진과 QMTL이 동일 Feature Store를 읽어 동일 데이터를 보도록 강제.
- `sr_integration_proposal.md`는 다음과 같이 Feature Store를 취급합니다.
  - 단기: `data_spec`/`data_context` 수준의 **스냅샷 핸들 계약 + 제출 시 샘플 검증**에 집중.
  - 중기 이후: 이 핸들 계약을 깨지 않는 선에서 `DataContext`를 확장하고,  
    백엔드로 공유 Feature Store를 도입하는 것을 **향후 고려 사항**으로 둠.

### 6.3 설계 레이어링

- **표현식/결과 레벨 일관성**  
  - `sr_integration_proposal.md`의 `expression_dag_spec` + `validation_sample` 핸드셰이크가 담당.  
  - 동일 데이터에서 SR 엔진과 QMTL이 **같은 수식 결과(S₁==S₂)**를 내는지 검증.
- **데이터/스냅샷 레벨 일관성**  
  - 이 문서의 `DataContext` + Feature Store 권장안이 담당.  
  - 둘이 **정확히 같은 universe/snapshot/feature_set**를 보도록 강제.

이 두 축을 조합하면, 초기에는 operon 통합 문서의 경량 `data_context`/핸드셰이크만으로도  
실용적인 수준의 일관성을 확보하고, 장기적으로는 Feature Store 기반 `DataContext`까지 확장해  
데이터 계보와 재현성을 강화하는 로드맵을 공유할 수 있습니다.
- [ ] 실시간 vs 배치 데이터 처리 구분

---

## 6. 다음 단계

1. 이 스케치 기반으로 논의
2. 결정된 내용을 `sr_integration_proposal.md` 섹션 12에 통합
3. DataContext 프로토콜 상세 설계
4. Feature Store 인터페이스 정의

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2025-11-27 | 초안 작성 (논의용 스케치) |
