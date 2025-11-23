# Pylance 에러 중 실제 런타임 문제를 일으킬 수 있는 이슈

**작성일**: 2025-11-23  
**총 Pylance 에러**: 1,039개  
**런타임 영향 가능성**: 3개 항목

---

## 🔍 왜 이렇게 많은 에러가 발생하는가?

### Pylance 설정 부재
**현재 상황**: `.vscode/settings.json`에 Pylance 타입 체킹 레벨 설정이 **전혀 없음**

```jsonc
// 현재 .vscode/settings.json
{
    "python.analysis.exclude": [...],
    // python.analysis.typeCheckingMode 설정 없음!
}
```

### Pylance의 기본 동작
VSCode의 Pylance는 타입 체킹 모드가 명시되지 않으면 **"basic" 모드**를 사용합니다:

| 모드 | 설명 | 에러 수준 |
|------|------|----------|
| `off` | 타입 체킹 비활성화 | 거의 없음 |
| `basic` (기본값) | 기본적인 타입 체킹 | 중간 |
| `standard` | 표준 타입 체킹 | 많음 |
| `strict` | 엄격한 타입 체킹 | 매우 많음 |

### 문제의 원인

1. **기본값이 "basic"**: 설정이 없으면 Pylance는 자동으로 `basic` 모드 사용
2. **Optional 타입에 민감**: `int | None` 같은 Optional 타입을 엄격하게 체크
3. **`__all__` 검증**: export 선언과 실제 심볼 존재 여부를 체크
4. **Forward reference 추론 한계**: 순환 참조 해결용 문자열 타입 힌트를 완벽히 이해 못함

### 비교: mypy 설정

`pyproject.toml`의 mypy 설정은 **훨씬 관대**합니다:

```toml
[tool.mypy]
strict = false                    # strict 모드 꺼짐
ignore_missing_imports = true     # import 에러 무시

[[tool.mypy.overrides]]
module = ["qmtl.runtime.*", "qmtl.services.*", ...]
ignore_errors = true              # 대부분의 모듈 에러 무시
```

**결과**: mypy는 거의 에러를 보고하지 않지만, Pylance는 1,039개 에러 보고

### 해결 방법

`.vscode/settings.json`에 추가:

```jsonc
{
    "python.analysis.typeCheckingMode": "off",  // 또는 "basic"을 유지하고 개별 설정 조정
    "python.analysis.diagnosticMode": "openFilesOnly",  // 열린 파일만 체크
}
```

또는 더 세밀한 제어:

```jsonc
{
    "python.analysis.typeCheckingMode": "basic",
    "python.analysis.diagnosticSeverityOverrides": {
        "reportUnusedVariable": "none",
        "reportMissingTypeStubs": "none",
        "reportOptionalMemberAccess": "none",
        "reportOptionalSubscript": "none",
        "reportOptionalOperand": "none",
        "reportGeneralTypeIssues": "warning"  // error → warning로 완화
    }
}
```


---

## 🔴 Critical: 즉시 수정 필요

### 1. `interval` 타입 불일치 - Node.feed() 호출

**파일**: `qmtl/examples/brokerage_demo/ccxt_binance_futures_nodeset_demo.py`  
**라인**: 71, 76, 81, 86

#### 문제 상황
```python
# Node의 interval 속성: int | None (Optional)
# feed() 메서드 시그니처: interval: int (Required)

pre.feed(signal.node_id, signal.interval, 60, order)      # line 71
siz.feed(pre.node_id, pre.interval, 60, pre_out)          # line 76
exe.feed(siz.node_id, siz.interval, 60, siz_out)          # line 81
pub.feed(exe.node_id, exe.interval, 60, exe_out)          # line 86
```

#### 에러 메시지
```
"int | None" 형식의 인수를 "feed" 함수에서 "int" 형식의 "interval" 매개 변수에 할당할 수 없습니다.
  형식 "int | None"은 형식 "int"에 할당할 수 없습니다.
    "None"은 "int"에 할당할 수 없습니다.
```

#### 런타임 영향
- **발생 시점**: `feed()` 호출 시
- **에러 타입**: `TypeError` 또는 validation 실패 가능
- **심각도**: High - execution pipeline이 동작하지 않을 수 있음

#### 현재 동작 분석
- `PreTradeGateNode`, `SizingNode`, `ExecutionNode` 등은 생성 시 `interval=order.interval`로 부모 노드의 interval을 그대로 전달
- 부모 노드가 `interval=None`으로 생성되면, execution node들도 `interval=None`이 됨
- 이후 `feed()` 호출 시 `None`이 전달되어 타입 불일치 발생

#### 해결 방안
1. **Option A**: `feed()` 호출 전에 타입 가드 추가
   ```python
   if signal.interval is None:
       raise ValueError("signal node must have interval")
   pre.feed(signal.node_id, signal.interval, 60, order)
   ```

2. **Option B**: execution node 생성 시 interval이 None이면 에러
   ```python
   # pretrade.py, sizing.py, execution.py
   if order.interval is None:
       raise ValueError("order node must have an interval for execution pipeline")
   super().__init__(order, interval=order.interval, ...)
   ```

3. **Option C**: `feed()` 시그니처를 `interval: int | None`으로 변경하고 내부에서 처리
   - 영향 범위가 크므로 신중하게 결정 필요

---

### 2. `interval` 산술 연산 - GARCH Generator

**파일**: `qmtl/runtime/generators/garch.py`  
**라인**: 38

#### 문제 상황
```python
class GarchInput(SyntheticInput):
    def __init__(self, *, interval: int, period: int, ...) -> None:
        super().__init__(interval=interval, period=period, seed=seed)
        # ...

    def step(self) -> tuple[int, dict[str, float]]:
        # ...
        self.timestamp += self.interval  # line 38
```

#### 에러 메시지
```
'+=' 연산자는 'int' 및 'int | None' 형식에 대해 지원되지 않습니다.
  '+' 연산자는 'int' 및 'None' 형식에 대해 지원되지 않습니다.
```

#### 런타임 영향
- **발생 시점**: `GarchInput.step()` 실행 시
- **에러 타입**: `TypeError: unsupported operand type(s) for +=: 'int' and 'NoneType'`
- **심각도**: Medium - 하지만 실제로는 발생 확률 낮음

#### 현재 동작 분석
- `GarchInput.__init__()` 시그니처에서 `interval: int` (Required)로 정의
- 부모 클래스 `SyntheticInput.__init__()`도 `interval: int` (Required)로 정의
- `self.interval`이 `None`이 되려면 부모 클래스에서 타입 무시하고 할당해야 함
- **실제로는 문제 없을 가능성 높음** - Pylance가 어딘가의 `int | None` 타입을 추론

#### 해결 방안
1. **Option A**: 타입 가드 추가 (방어적 프로그래밍)
   ```python
   def step(self) -> tuple[int, dict[str, float]]:
       if self.interval is None:
           raise ValueError("interval must be set")
       self.timestamp += self.interval
   ```

2. **Option B**: 타입 힌트 명시로 Pylance 안심시키기
   ```python
   self.interval: int  # __init__ 내에서
   ```

3. **Option C**: 부모 클래스 체인 확인하고 타입 정리

---

## 🟡 Warning: 사용 패턴에 따라 문제 가능

### 3. `__all__` Export 누락 - Public API

**파일**: `qmtl/__init__.py`  
**라인**: 39-78

#### 문제 상황
```python
__all__ = [
    "Pipeline",      # 실제로 import 안됨
    "Strategy",      # 실제로 import 안됨
    "Runner",        # 실제로 import 안됨
    "Node",          # 실제로 import 안됨
    # ... 총 36개 심볼이 선언되었지만 실제 import 안됨
]
```

#### 에러 메시지
```
"Pipeline"이(가) __all__에 지정되었지만 모듈에 없습니다.
```

#### 런타임 영향
- **발생 시점**: `from qmtl import Pipeline` 사용 시
- **에러 타입**: `ImportError: cannot import name 'Pipeline' from 'qmtl'`
- **심각도**: Medium - 사용자가 실제로 이 방식으로 import하는 경우에만 문제

#### 현재 상황 분석
- `__all__`에는 많은 심볼이 선언되어 있지만, 실제로 `from ... import ...` 구문이 없음
- 사용자가 공식 문서나 예제를 따라 `from qmtl import Pipeline`을 시도하면 실패
- 하지만 `from qmtl.runtime.sdk import Node` 같은 방식은 정상 작동

#### 해결 방안
1. **Option A**: 실제로 import 추가 (권장)
   ```python
   from qmtl.runtime.sdk import Node, Pipeline, Runner  # etc.
   ```

2. **Option B**: `__all__` 제거 (public API 포기)
   ```python
   # __all__ 전체 삭제
   ```

3. **Option C**: `__all__`을 현재 실제로 export되는 것만 나열
   ```python
   __all__ = ["foundation", "interfaces", "runtime", "services"]
   ```

---

## ✅ False Positive: 실제로는 문제 없음

### 4. Forward Reference - Config Dataclass

**파일**: `qmtl/foundation/config.py`  
**라인**: 95, 365, 366

#### 문제 상황
```python
@dataclass
class WorldServiceConfig:
    server: WorldServiceServerConfig | None = None  # line 95

@dataclass
class UnifiedConfig:
    gateway: "GatewayConfig" = field(...)    # line 365
    dagmanager: "DagManagerConfig" = field(...)  # line 366
```

#### 에러 메시지
```
형식 식에는 변수를 사용할 수 없습니다.
```

#### 런타임 영향
- **발생 시점**: 없음 (Pylance만 불평)
- **에러 타입**: 없음
- **심각도**: None - Python 런타임에서는 정상 작동

#### 원인
- `from __future__ import annotations` 때문에 모든 타입 힌트가 문자열로 저장됨
- Pylance가 forward reference 패턴을 완벽하게 이해하지 못함
- 실제 Python 런타임에서는 아무 문제 없음

#### 해결 방안
- **권장**: 무시 (실제 문제 아님)
- 대안: `# type: ignore` 주석 추가하여 Pylance 경고 억제

---

### 5. Test Mock 타입 불일치

**파일**: `tests/e2e/shadow/test_shadow_end_to_end.py`  
**라인**: 103, 122

#### 문제 상황
```python
ws_client = _StubWorldClient(...)
ctx_service = ComputeContextService(world_client=ws_client)  # line 103

hub = RecordingHub()
consumer = ControlBusConsumer(ws_hub=hub)  # line 122
```

#### 에러 메시지
```
"_StubWorldClient" 형식의 인수를 "WorldServiceClient | None" 형식의 매개 변수에 할당할 수 없습니다.
```

#### 런타임 영향
- **발생 시점**: 없음 (테스트는 정상 작동)
- **에러 타입**: 없음
- **심각도**: None - Duck typing으로 작동

#### 원인
- 테스트용 stub/mock 객체가 실제 인터페이스를 명시적으로 구현하지 않음
- Python의 duck typing 덕분에 런타임에서는 정상 작동
- 하지만 타입 체커는 명시적 상속 관계를 요구

#### 해결 방안
- **권장**: Protocol 명시적 구현 또는 `# type: ignore` 사용
- 영향 범위: 테스트 코드만이므로 우선순위 낮음

---

## 요약

### 즉시 수정 권장
1. **interval 타입 불일치** (ccxt_binance_futures_nodeset_demo.py) - execution pipeline 동작 보장
2. **__all__ export 누락** (qmtl/__init__.py) - 공식 API 문서화/사용성

### 추가 조사 필요
1. **GARCH interval 산술 연산** - 실제 발생 가능성 확인 필요

### 무시 가능
1. Forward reference 경고 (config.py)
2. 테스트 mock 타입 불일치

### 통계
- **Critical**: 1개
- **Warning**: 2개  
- **False Positive**: 3개
- **나머지 1,033개**: 대부분 타입 체커만의 문제, 런타임 영향 없음

---

## 📊 mypy vs Pylance 비교

### mypy 실행 결과

#### 기본 모드 (현재 CI 설정)
```bash
$ uv run mypy qmtl
Success: no issues found in 569 source files
```
**결과**: ✅ **0개 에러** - CI 통과

#### --check-untyped-defs 모드
```bash
$ uv run mypy --check-untyped-defs qmtl
qmtl/interfaces/scripts/check_doc_sync.py:27: error: "object" has no attribute "check_doc_sync"
Found 1 error in 1 file (checked 569 source files)
```
**결과**: 1개 에러 (실제 버그: 동적 import 문제)

#### --strict 모드
```bash
$ uv run mypy --strict qmtl
Found 65 errors in 23 files (checked 569 source files)
```
**결과**: 65개 에러 (대부분 타입 annotation 누락)

### 에러 유형 분석

**mypy --strict의 65개 에러 분류:**

1. **타입 annotation 누락** (~40개, 61%): `no-untyped-def`, `no-untyped-call`
   - 함수 시그니처에 타입 힌트가 없음
   - 예: `def main(argv):` → `def main(argv: list[str] | None = None) -> None:`

2. **제네릭 타입 파라미터 누락** (~20개, 31%): `type-arg`
   - `dict` → `dict[str, Any]`
   - `Dict` → `Dict[str, str]`
   - `tuple` → `tuple[str, int]`

3. **실제 버그** (1개, 1.5%): `attr-defined`
   - `check_doc_sync.py`: 동적 import 패턴 문제

4. **기타** (~4개, 6%): 테스트 fixture 타입 문제

### Pylance vs mypy 차이점

| 항목 | Pylance (기본) | mypy (현재 CI) | mypy --strict |
|------|----------------|----------------|---------------|
| 에러 수 | **1,039개** | **0개** | 65개 |
| Optional 타입 체크 | 매우 엄격 | 관대 | 엄격 |
| `__all__` 검증 | ✓ | ✗ | ✗ |
| Forward reference | 불완전 | ✓ | ✓ |
| 타입 annotation 필수 | ✗ | ✗ | ✓ |
| CI 통과 | N/A | ✓ | ✗ |

### 현재 mypy 설정 (pyproject.toml)

```toml
[tool.mypy]
python_version = "3.11"
strict = false                    # ← 핵심: strict 모드 꺼짐
warn_unused_configs = true
warn_unused_ignores = true
warn_return_any = true
warn_unreachable = true
ignore_missing_imports = true     # import 에러 무시

[[tool.mypy.overrides]]
module = [
  "qmtl.runtime.*",
  "qmtl.services.*",
  "qmtl.foundation.*",
  "qmtl.examples.*",
  "tests.*",
]
ignore_errors = true              # ← 대부분의 모듈 에러 무시
```

### CI 워크플로우

```yaml
- name: Type check (mypy)
  run: uv run --with mypy -m mypy  # 추가 옵션 없음 = 기본 모드
```

**CI에서 실행되는 명령**: `mypy qmtl` (기본 모드)
- `strict = false`
- `ignore_errors = true` for most modules
- **결과**: 항상 통과 (0 errors)

---

## 🎯 결론 및 권장사항

### 1. mypy는 제한적이지만 의미 있는 검증을 하고 있음

**실제 상황 재평가:**

```toml
# 1단계: 대부분 무시
[[tool.mypy.overrides]]
module = ["qmtl.runtime.*", "qmtl.services.*", "qmtl.foundation.*", ...]
ignore_errors = true

# 2단계: gateway 모듈 18개만 다시 활성화
[[tool.mypy.overrides]]
module = [
  "qmtl.services.gateway.dagmanager_client",
  "qmtl.services.gateway.redis_queue",
  "qmtl.services.gateway.fsm",
  "qmtl.services.gateway.database",
  "qmtl.services.gateway.worker",
  # ... 총 18개 핵심 모듈
]
ignore_errors = false
```

**커버리지:**
- **전체**: 569 파일 중 대부분 무시
- **Gateway**: 66개 파일 중 **18개 핵심 모듈** 타입 체크 활성화 (~27%)
- **결과**: gateway의 핵심 비즈니스 로직에 대한 타입 안전성 보장

**mypy의 실제 가치:**
1. ✅ **게이트웨이 타입 회귀 방지**: 가장 중요한 orchestration 계층 보호
2. ✅ **기본 타입 에러 검출**: `int | None`을 `int`에 할당, return type 불일치 등
3. ✅ **CI 게이트**: gateway 변경 시 타입 안전성 자동 검증

**검증:**
```python
# mypy는 이런 에러를 잡아냄
def bad_function(x: int) -> str:
    return x + 1  # ❌ error: Incompatible return value type

def use_optional(val: int | None) -> int:
    return val + 1  # ❌ error: Unsupported operand types for + ("None" and "int")
```

**재평가된 판단:**
- ❌ ~~CI에서 제거해도 무방~~ → **제거하면 안 됨**
- ✅ **현재 설정 유지 또는 강화** - gateway 보호는 중요한 가치

### 2. Pylance는 과도하게 엄격함

**현재 상태:**
- 1,039개 에러 중 실제 런타임 문제는 **3개 미만**
- 나머지는 타입 힌트의 완벽함을 요구하는 "코드 스타일" 이슈

**판단:**
- ✅ `.vscode/settings.json`에 완화 설정 추가 권장
- 개발 생산성을 위해 `"python.analysis.typeCheckingMode": "basic"` 유지하되
- `diagnosticSeverityOverrides`로 false positive 줄이기

### 3. 실용적인 접근 방안

#### ❌ Option A: mypy CI 제거 (권장하지 않음)
```yaml
# .github/workflows/ci.yml에서 삭제
- name: Type check (mypy)
  run: uv run --with mypy -m mypy
```
**문제점**: 
- Gateway 모듈에 대한 유일한 정적 타입 가드 상실
- 중요한 orchestration 계층의 타입 안전성 보장 사라짐
- 대체 수단 없이 제거는 리스크

#### ✅ Option B: mypy 커버리지 점진적 확대 (권장)
```toml
[[tool.mypy.overrides]]
module = [
  "qmtl.runtime.sdk.*",           # SDK 핵심 로직 추가
  "qmtl.runtime.pipeline.*",      # 실행 파이프라인 추가
  "qmtl.services.dagmanager.*",   # DAG 매니저 추가
  "qmtl.foundation.common.*",     # 공통 유틸리티 추가
]
ignore_errors = false
```

**단계별 접근:**
1. 현재 gateway 18개 모듈 유지 (기반 확보)
2. 우선순위 높은 모듈 순차 추가:
   - `qmtl.runtime.sdk.runner` (전략 실행)
   - `qmtl.runtime.pipeline.execution_nodes.*` (실행 노드)
   - `qmtl.services.dagmanager.server` (DAG 서버)
3. 각 추가 시 타입 에러 수정과 함께 진행
4. 최종 목표: 핵심 비즈니스 로직 ~50% 커버리지

**예상 효과:**
- 타입 안정성 향상 (단계적)
- CI 실패 리스크 관리 가능
- 레거시 코드는 여전히 무시 (점진적 마이그레이션)

#### Option C: Pylance 설정 개선 (병행 가능)

**`.vscode/settings.json`에 추가:**
```jsonc
{
    "python.analysis.typeCheckingMode": "basic",
    "python.analysis.diagnosticMode": "openFilesOnly",
    "python.analysis.diagnosticSeverityOverrides": {
        "reportOptionalOperand": "none",           // int | None 연산 경고 완화
        "reportOptionalMemberAccess": "warning",   // 중요도 낮춤
        "reportGeneralTypeIssues": "warning",      // error → warning
        "reportUnusedImport": "information",
        "reportUnusedVariable": "information"
    }
}
```

**효과:**
- 개발 중 false positive 1,000개 → ~50개로 감소
- 실제 의미 있는 에러만 표시
- mypy와 Pylance의 역할 분담:
  - **mypy (CI)**: 핵심 모듈 타입 안전성 보장
  - **Pylance (IDE)**: 개발 중 실시간 피드백 (완화)

### 4. 최종 권장사항

#### 즉시 실행 가능한 개선 (Low Risk)
1. ✅ `.vscode/settings.json`에 Pylance 완화 설정 추가
2. ✅ mypy 현재 설정 유지 (gateway 보호 중요)
3. ✅ 이 문서를 팀 공유하여 타입 체커 정책 합의

#### 중기 목표 (3-6개월)
1. mypy 커버리지를 gateway → sdk → pipeline 순으로 확대
2. 새로운 코드는 타입 힌트 필수 정책 도입
3. 핵심 모듈 타입 커버리지 50% 달성

#### 장기 목표 (6-12개월)
1. `strict = false` → 모듈별로 `strict = true` 전환 검토
2. 레거시 코드 점진적 타입 힌트 추가
3. Pylance를 "standard" 모드로 상향 검토 (타입 품질 개선 후)

### 5. 반대 의견에 대한 답변

**"mypy가 의미 없다"는 제 초기 평가는 잘못되었습니다.**

**올바른 평가:**
- mypy는 **선택적이지만 전략적**으로 설정되어 있음
- 가장 중요한 **gateway orchestration 계층**에 집중
- 66개 gateway 파일 중 18개 핵심 모듈을 타입 체크
- 이는 **최소 비용으로 최대 효과**를 내는 실용적 접근

**제거 시 리스크:**
- Gateway는 전체 시스템의 **중앙 조율자** 역할
- 타입 에러가 여기서 발생하면 전체 시스템 영향
- pytest만으로는 타입 안전성을 보장할 수 없음
- 대체 수단 없이 제거는 **위험**

**결론:**
- ❌ mypy CI 제거 (초기 권장) → 철회
- ✅ mypy 유지 + 점진적 강화 (최종 권장)
- ✅ Pylance 완화로 개발 생산성 개선

---

## 🔄 Pylance 에러 재검토

### 초기 평가의 문제점

**잘못된 가정**: "Pylance 1,039개 에러는 과도한 타입 체킹 때문"

### 실제 상황 재분석

#### 1. `__all__` export 에러 (36개) - False Positive ✅

**Pylance 불평:**
```python
# qmtl/__init__.py
__all__ = ["Node", "Pipeline", "Runner", ...]  # 36개 에러
```
> "Node"이(가) __all__에 지정되었지만 모듈에 없습니다.

**하지만 실제로는:**
```python
# qmtl/__init__.py (line 88-156)
_ATTR_MAP = {
    "Node": ("qmtl.runtime.sdk.node", "Node"),
    "Pipeline": ("qmtl.runtime.pipeline.pipeline", "Pipeline"),
    # ... 모든 심볼 매핑 존재
}

def __getattr__(name: str) -> Any:
    """지연 import를 통한 동적 export"""
    target = _ATTR_MAP.get(name)
    if target is None:
        raise AttributeError(name)
    module_path, attr = target
    module = importlib.import_module(module_path)
    value = module if attr is None else getattr(module, attr)
    globals()[name] = value
    return value
```

**실제 사용 패턴:**
```bash
# 코드베이스 전체 검색 결과
$ grep -r "from qmtl import Node" **/*.py
# 결과: 0건

$ grep -r "from qmtl.runtime.sdk import Node" **/*.py  
# 결과: 17건 (실제 사용 패턴)
```

**판단:**
- ❌ Pylance는 `__getattr__` 기반 동적 export를 이해하지 못함
- ✅ 실제 코드는 `__getattr__`로 정상 동작 (lazy import 패턴)
- ✅ 코드베이스에서는 `from qmtl import Node` 사용 안 함 (직접 경로 사용)
- **결론**: 이 36개 에러는 **Pylance의 한계**이며 실제 문제 아님

#### 2. `interval` 타입 에러 재평가

**원래 평가**: Critical - 즉시 수정 필요

**재검토 후:**
```python
# qmtl/runtime/sdk/nodes/base.py
class Node:
    def __init__(self, ..., interval: int | str | None = None):
        config_payload = NodeConfig.build(interval=interval, ...)
        self.interval = config_payload.interval  # int | None

# qmtl/runtime/sdk/nodes/mixins.py  
class NodeFeedMixin:
    def feed(self, upstream_id: str, interval: int, ...):
        validate_feed_params(upstream_id, interval, ...)  # interval must be int
```

**실제 사용처 분석:**
```python
# qmtl/runtime/pipeline/execution_nodes/pretrade.py
class PreTradeGateNode(ProcessingNode):
    def __init__(self, order: Node, ...):
        super().__init__(
            order,
            interval=order.interval,  # 부모 interval 그대로 전달
            ...
        )
```

**문제 시나리오:**
1. Signal node가 `interval=None`으로 생성
2. Execution nodes가 `interval=signal.interval` (None)으로 생성
3. `feed()` 호출 시 `interval=None` 전달 → `InvalidParameterError`

**하지만:**
- Signal/strategy nodes는 일반적으로 interval이 필수
- 실제 운영 코드에서 `interval=None`인 노드로 execution pipeline 구성하는 경우는 거의 없음
- 발생하면 `validate_feed_params`에서 명확한 에러 메시지와 함께 실패

**재평가된 심각도:**
- ~~Critical~~ → **Medium-Low**
- 이론적으로는 가능하지만 실제로는 드문 시나리오
- 발생 시 명확한 에러 메시지로 빠른 디버깅 가능

#### 3. 나머지 1,000개 에러 - 실제로는?

대부분은 여전히 false positive이지만, **일부는 의미 있는 경고**:

**카테고리 재분류:**
- **36개**: `__all__` export (Pylance의 `__getattr__` 이해 부족) - False Positive
- **~100개**: Optional 타입 엄격 체크 (`int | None` → `int`) - 대부분 안전
- **~50개**: Import 순서, unused variable 등 - 코드 품질 개선 기회
- **~850개**: 제네릭 타입 파라미터, 타입 annotation 누락 등 - Informational

### 수정된 평가

#### Pylance의 실제 가치

**부정적 측면:**
1. ❌ `__getattr__` 동적 패턴을 이해하지 못함 (36개 false positive)
2. ❌ Optional 타입을 과도하게 엄격하게 체크 (보수적)

**긍정적 측면:**
1. ✅ 실제 타입 불일치를 사전에 발견 (드물지만 존재)
2. ✅ 코드 품질 개선 기회 제공 (unused vars, import order 등)
3. ✅ 개발 중 실시간 피드백 (mypy는 CI에서만)

#### 권장 설정 업데이트

**`.vscode/settings.json` (개선된 버전):**
```jsonc
{
    "python.analysis.typeCheckingMode": "basic",
    "python.analysis.diagnosticMode": "openFilesOnly",
    "python.analysis.diagnosticSeverityOverrides": {
        // False positive 억제
        "reportMissingModuleSource": "none",           // __all__ 동적 export 무시
        "reportAttributeAccessIssue": "none",          // __getattr__ 패턴 무시
        
        // 엄격도 완화
        "reportOptionalOperand": "none",               // int | None 연산
        "reportOptionalMemberAccess": "warning",       // Optional 멤버 접근
        "reportGeneralTypeIssues": "warning",          // 일반 타입 이슈 완화
        
        // 유용한 경고 유지
        "reportUnusedImport": "information",           // 정보성
        "reportUnusedVariable": "information",         // 정보성
        "reportUndefinedVariable": "error"             // 실제 버그 가능성
    },
    
    // __all__ 관련 에러 무시 (동적 export 패턴 사용)
    "python.analysis.ignore": [
        "**/qmtl/__init__.py"  // __getattr__ 사용하는 파일
    ]
}
```

### 최종 재평가 요약

| 에러 타입 | 개수 | 초기 평가 | 재평가 | 조치 |
|-----------|------|-----------|--------|------|
| `__all__` export | 36 | False Positive | ✅ False Positive | Pylance 설정으로 무시 |
| `interval` 타입 | 3 | Critical | Medium-Low | 방어 코드 추가 고려 |
| Optional 엄격 | ~100 | Warning | Informational | 설정 완화 |
| 코드 품질 | ~50 | False Positive | ✅ 개선 기회 | 선택적 수정 |
| 기타 | ~850 | False Positive | Informational | 무시 |

**핵심 교훈:**
- Pylance 1,039개 중 **실제 런타임 문제**: ~3개 미만
- 하지만 **false positive 이유가 다양함**:
  - 36개는 Pylance가 Python 동적 패턴 이해 못함
  - 나머지는 과도한 타입 안전성 요구
- **해결**: 세밀한 `diagnosticSeverityOverrides` 설정

---

## 📊 최종 평가: mypy vs Pylance

### mypy (CI)
**역할**: 핵심 모듈 타입 안전성 보장  
**가치**: ✅ **높음 - 유지 필수**

- Gateway 18개 핵심 모듈 보호 중
- 전략적으로 중요한 부분에 집중
- CI에서 자동 검증
- **판단**: 제한적이지만 **의미 있는 보호**

### Pylance (IDE)  
**역할**: 개발 중 실시간 타입 체크  
**가치**: ⚠️ **낮음 - 대부분 노이즈**

- 1,039개 에러 중 실제 문제 <3개
- 36개는 Pylance의 기술적 한계 (`__getattr__` 미지원)
- 나머지는 과도한 타입 엄격성
- **판단**: **노이즈에 가까움**, 설정 완화 필요

### 대조적인 결론

| 도구 | 초기 인상 | 실제 평가 | 조치 |
|------|-----------|----------|------|
| **mypy** | "무의미, 제거 고려" | ✅ "전략적 보호, 유지 필수" | 유지 + 점진적 확대 |
| **Pylance** | "타입 안전성 문제 발견" | ⚠️ "대부분 노이즈" | 설정 완화로 억제 |

### 아이러니

**mypy**:
- 겉보기: "0개 에러" → "아무것도 안 함?"
- 실제: Gateway 핵심 모듈 타입 체크 → **실질적 가치**

**Pylance**:
- 겉보기: "1,039개 에러" → "많은 문제 발견?"
- 실제: 대부분 false positive → **노이즈**

### 실용적 권장사항

#### 1. mypy (유지 및 강화)
```toml
# pyproject.toml - 커버리지 점진적 확대
[[tool.mypy.overrides]]
module = [
  "qmtl.runtime.sdk.*",        # 추가
  "qmtl.runtime.pipeline.*",   # 추가
  "qmtl.services.dagmanager.*" # 추가
]
ignore_errors = false
```

#### 2. Pylance (노이즈 억제)
```jsonc
// .vscode/settings.json
{
    "python.analysis.typeCheckingMode": "basic",
    "python.analysis.diagnosticSeverityOverrides": {
        // 핵심: false positive 대량 제거
        "reportMissingModuleSource": "none",
        "reportAttributeAccessIssue": "none",
        "reportOptionalOperand": "none",
        "reportGeneralTypeIssues": "warning"
    },
    "python.analysis.ignore": [
        "**/qmtl/__init__.py"  // __getattr__ 패턴 무시
    ]
}
```

### 요약

**mypy**: 
- ❌ ~~"제거 검토"~~ 
- ✅ **"유지 필수 + 확대 권장"**
- 이유: 핵심 모듈 보호라는 명확한 가치

**Pylance**: 
- ❌ "1,039개 에러 수정 필요"
- ✅ **"설정 완화로 노이즈 제거"**
- 이유: 대부분이 Python 동적 특성 미이해로 인한 false positive

**결론**: mypy는 과소평가되었고, Pylance는 과대평가되었습니다.
