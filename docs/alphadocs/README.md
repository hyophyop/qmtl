# AlphaDocs

이 디렉터리는 연구 노트와 전략 아이디어의 원천 문서를 보관합니다.
`ideas/` 하위 폴더는 아이디어 이력 관리가 목적이며 직접 구현하지 않습니다.
더 높은 성능의 모델로 정제된 아이디어(예: `ideas/gpt5pro/`)만 실제 구현 대상으로 삼습니다.
각 문서는 `docs/alphadocs_registry.yml`에 등록되어 구현 상태와 관련 모듈을 추적합니다.
문서 수정이나 이동 시에는 `docs/alphadocs_history.log`를 업데이트하세요.
필요한 QMTL transform과 테스트 범위를 명시한 `QMTL Integration` 섹션을 각 문서에 추가하고,
레지스트리의 `modules` 필드에는 해당 transform과 이를 사용하는 전략 노드 경로를 모두 포함하세요.
