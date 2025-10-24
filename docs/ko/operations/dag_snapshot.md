# DAG 스냅샷 및 프리즈

`snapshot` 서브커맨드를 사용해 DAG 정의를 캡처하거나 검증할 수 있습니다.

```bash
qmtl service dagmanager snapshot --file dag.json --freeze
qmtl service dagmanager snapshot --file dag.json --verify
```

- `--freeze` 는 SHA-256 해시와 DAG 페이로드를 포함한 스냅샷을 기록합니다(기본 경로: `dag.snapshot.json`).
- `--verify` 는 현재 DAG가 이전에 프리즈한 스냅샷과 일치하는지 확인하고 일치하지 않으면 비영(0이 아닌) 상태 코드로 종료합니다.

이 워크플로는 실행 간에 DAG의 `code_hash`, `schema_hash` 가 변하지 않도록 보장해 전략 또는 노드 버전을 고정하는 데 유용합니다.
