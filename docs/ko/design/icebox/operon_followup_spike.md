---
title: "Operon 후속 통합 및 pyoperon 스파이크 노트"
tags: [design, sr, operon, spike]
author: "QMTL Team"
last_modified: 2025-11-27
status: draft
related: sr_integration_proposal.md
---

# Operon 후속 통합 및 pyoperon 스파이크 노트

!!! warning "Icebox (참고용, 현재 작업 대상 아님)"
    이 문서는 `docs/ko/design/icebox/`에 보관된 참고용 스파이크 노트입니다. **현재 작업 대상(SSOT)** 이 아니며, 필요 시 배경/아이디어 참고로만 사용하세요. 채택한 내용은 `docs/ko/architecture/` 또는 코드/테스트로 승격해 반영합니다.

!!! warning "범위"
    - 본 문서는 **Operon/pyoperon 기반 통합의 후속 과제**를 정리한 별도 노트입니다.  
    - QMTL SR 통합의 1차 엔진은 `PySR`을 기준으로 진행하며, Operon은 **추후 추가**합니다.  
    - 메인 설계는 `sr_integration_proposal.md`를 참고하세요.

## pyoperon 스파이크 체크리스트

본격적인 Operon 통합 전에, pyoperon의 제약/특성을 빠르게 확인하기 위한 실험 항목입니다.

1. **환경/기본 사용법 확인**
   - pyoperon 설치 후 간단한 수식(예: `EMA(close, 20) - EMA(close, 50)`)으로 개체 생성·평가.
   - 표현식 문자열, 트리/AST, 피트니스 값을 출력해 기본 동작 확인.

2. **표현식/AST/직렬화 파악**
   - `Individual` 등에서 expression string, 내부 트리/AST 추출.
   - AST를 JSON 등 직렬화 가능한 형태로 덤프해 샘플 수집.
   - `ExpressionDagSpec`에 1:1 매핑 가능한지 검토.

3. **연산자/함수 지원 범위 정리**
   - 산술/비교/논리/조건/수학 내장 함수 목록화.
   - DAG 노드 매핑 가능/불가를 구분해 **지원 연산 화이트리스트** 작성.

4. **expression_key/정규화 실험**
   - 동치 수식(`a*b` vs `b*a`, `a+0` vs `a`)으로 AST 비교.
   - 정규화 후 SHA-256 등으로 key 생성 → 동치/비동치 판별력 확인.

5. **수치/결정론 특성 측정**
   - 동일 입력 반복 평가 시 float 오차, NaN/Inf, 0-division 등 관찰.
   - QMTL 실행기 대비 오차 범위 측정 → epsilon/NaN 정책 확정.

6. **복잡도/트리 구조 특성 확인**
   - 여러 세대 개체의 `tree_depth`/`num_nodes` 분포 수집.
   - DAG 변환 시 예상 노드/에지 수 → 복잡도 컷오프 기준 설정 참고.

7. **간단한 DAG 변환 프로토타입**
   - 제한 연산 서브셋({+, -, *, /, 비교, 단순 함수}) 대상으로
     수식 → AST → 임시 DAG 스펙 → QMTL DAG → 출력 비교까지 end-to-end 확인.

8. **의존성/호환성 확인**
   - Python 버전 요구, 설치 방식(pip/conda/소스 빌드), API 변경 주기 조사.
   - `qmtl[sr]` extras 버전 고정/범위 전략 초안 마련.

9. **피트니스/예외 처리**
   - 사용자 정의 피트니스 훅 지원 방식, 잘못된 수식/평가 실패 시 예외 패턴 확인.
   - SR 어댑터에서 예외를 제출 reject로 변환하는 패턴 스케치.

## Operon 특화 어댑터 (예시)

```python
# qmtl/integrations/sr/adapters/operon.py

from dataclasses import dataclass
from ..types import BaseSRCandidate


@dataclass
class OperonCandidate(BaseSRCandidate):
    """Operon 특화 후보 구현
    
    Operon의 추가 메타데이터를 포함합니다.
    """
    tree_depth: int = 0
    num_nodes: int = 0
    
    def get_id(self) -> str:
        return self.metadata.get("id", f"operon_{self.generation}_{hash(self.expression) % 10000:04d}")


class OperonAdapter:
    """Operon → SRCandidate 변환 어댑터"""
    
    @staticmethod
    def from_operon_result(operon_individual) -> OperonCandidate:
        """Operon의 Individual 객체를 OperonCandidate로 변환"""
        return OperonCandidate(
            expression=str(operon_individual.expression),
            metadata={
                "id": operon_individual.id,
                "generation": operon_individual.generation,
            },
            fitness=operon_individual.fitness,
            complexity=operon_individual.complexity,
            generation=operon_individual.generation,
            tree_depth=operon_individual.tree_depth,
            num_nodes=operon_individual.num_nodes,
        )
```

!!! note "pyoperon 빌드/배포 메모"
    - Apple Silicon에서 공식 wheel의 RPATH 문제가 있을 수 있으므로, 필요 시 `maturin build --release`로 ARM64 wheel을 재빌드하는 방안을 고려합니다.
    - 상세 빌드/호환성 기록은 스파이크 결과에 따라 추가합니다.
