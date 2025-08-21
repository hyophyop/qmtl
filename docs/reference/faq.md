{{ nav_links() }}

# FAQ

## 태그 기반 노드는 각 실행 모드에서 어떻게 동작하나요?

`TagQueryNode`는 Runner가 생성하는 `TagQueryManager`가 Gateway와 통신하여 큐 목록을 갱신합니다. `backtest`, `dryrun`, `live` 모드에서는 `--gateway-url`을 지정하면 태그 기반 노드를 완전히 사용할 수 있습니다. `offline` 모드는 Gateway 없이 로컬에서만 실행하므로 태그 기반 노드는 빈 큐 목록으로 초기화되어 동작이 부분적입니다. 필요한 경우 개별 지표를 `StreamInput`으로 등록하고 과거 데이터를 직접 백필하여 사용하세요.

{{ nav_links() }}

