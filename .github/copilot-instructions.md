# Architecture Overview
architecture.md, gateway.md, dag-manager.md 파일을 참조하여 시스템 아키텍처를 이해합니다. 이 문서는 각각 시스템의 주요 구성 요소인 SDK, gateway, dag-manager와 그 상호작용을 설명합니다.


# 기본 개발 가이드
## Soc (Separation of Concerns)
- 각 모듈은 단일 책임 원칙을 준수해야 합니다.
- 각 모듈은 명확한 책임을 가지고 있으며, 다른 모듈과의 의존성을 최소화해야 합니다.
- 모듈 간의 의존성은 인터페이스를 통해 관리해야 합니다.
- 각 모듈은 독립적으로 테스트 가능해야 합니다.
- 모든 모듈은 문서화되어야 하며, 변경 사항은 즉시 반영해야 합니다.
- 작업 중 기존 코드베이스에서 SoC를 위반하는 부분을 발견하면, 해당 부분을 리팩토링하여 SoC를 준수하도록 수정하는 것을 우선시해야 합니다.

## 개발 사이클
- 구현 후에 반드시 대응하는 테스트를 작성 및 실행해야 합니다.
- 테스트는 가능한 한 독립적이어야 하며, 다른 테스트에 의존하지 않아야 합니다.
- 테스트는 명확하고 이해하기 쉬워야 하며, 실패 시 원인을 쉽게 파악할 수 있어야 합니다.
- 테스트 실패 시 즉시 원인을 파악하고 수정해야 합니다.