# Labeling 계약/가드레일 (delayed label, no look-forward)

## 목적

라벨링은 실거래/서빙 파이프라인에서 **미래를 보지 않도록 구조적으로 누수가 불가능한 계약**을 제공해야 한다. 본 문서는 라벨 생성 시점, 입력/출력 스키마, 그리고 누수 방지 원칙을 정의한다.

## 핵심 불변식

1. **라벨은 entry_time=t에 생성되지 않는다.**
   - 라벨은 오직 resolved_time=t* (PT/SL hit 또는 timeout) 이후에만 emit한다.
2. **PT/SL/Time 파라미터는 t에서 계산/고정(freeze)된다.**
   - t 이후에 파라미터가 변하면 누수 위험이 생기므로 금지한다.
3. **비용/슬리피지 보정은 t에서 알 수 있는 모델/파라미터만 사용한다.**
4. **라벨 노드는 “학습/평가 출력”이며 주문/의사결정 입력으로 연결되지 않는다.**

## 용어

- **entry_time (t)**: 포지션 진입(또는 라벨 계산 기준) 시점.
- **resolved_time (t\*)**: PT/SL hit 또는 timeout으로 라벨이 확정되는 시점.
- **BarrierSpec**: PT/SL 임계값과 단위.
- **HorizonSpec**: 라벨 타임아웃 조건(시간/바 수 등).
- **LabelEvent**: 확정된 라벨 이벤트(학습/평가용).

## 스키마 계약

공용 타입은 `qmtl/runtime/labeling/schema.py`에 정의되며, `entry_time` 기준으로 파라미터가 고정되어야 한다.

```python
from qmtl.runtime.labeling import BarrierSpec, HorizonSpec, LabelEvent, LabelOutcome
```

### BarrierSpec

- `profit_target`: PT 임계값 (없으면 None)
- `stop_loss`: SL 임계값 (없으면 None)
- `unit`: 값의 의미(기본 "return_multiple")
- `frozen_at`: 파라미터가 고정된 시각 (entry_time과 동일해야 함)

### HorizonSpec

- `max_duration`: 최대 보유 시간
- `max_bars`: 최대 바 수
- `frozen_at`: 파라미터가 고정된 시각 (entry_time과 동일해야 함)

### LabelEvent

- `entry_time`, `resolved_time`은 반드시 `resolved_time >= entry_time`을 만족한다.
- `barrier.frozen_at`과 `horizon.frozen_at`이 설정된 경우 `entry_time`과 동일해야 한다.
- `outcome`은 `profit_target`, `stop_loss`, `timeout` 중 하나다.
- `cost_model_id`, `slippage_model_id`는 entry_time에 사용된 모델 식별자를 기록한다.

## 누수 방지 설계 원칙

### 1) 시간 축 분리

- **라벨링 노드는 `resolved_time` 이후에만 이벤트를 emit**한다.
- 라벨링 계산은 과거/현재 데이터만 읽는다.
- 라벨 출력은 주문/의사결정 입력으로 연결하지 않는다.

### 2) 파라미터 동결

- PT/SL/Timeout 파라미터는 `entry_time`에 동결(freeze)된다.
- 라벨 처리 중 변경되는 파라미터는 누수 가능성이 있으므로 금지한다.

### 3) 비용/슬리피지 보정 규칙

- 비용/슬리피지 보정은 `entry_time`에서 알 수 있는 모델/파라미터만 사용한다.
- 미래 데이터 기반의 동적 비용 모델을 라벨에 적용하지 않는다.

## 라벨 노드 연결 가드레일

- 라벨 노드는 학습/평가 출력으로만 사용한다.
- 주문/의사결정 입력으로 연결하지 않으며, DAG/노드셋 설계 시 이를 가드한다.
- 라벨 출력이 주문/리스크 노드로 들어가는 경로는 테스트에서 차단해야 한다.

## 후속 구현 참고

- 라벨링과 관련된 노드/변환은 `qmtl/runtime/nodesets/*`, `qmtl/runtime/indicators/*`, `qmtl/runtime/transforms/*`에서 본 계약을 준수하도록 한다.
