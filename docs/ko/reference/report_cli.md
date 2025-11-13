# Report CLI

`qmtl report` 명령은 `returns` 배열을 포함하는 JSON 파일로부터 간단한 성과 리포트를 생성합니다.

```bash
qmtl report --from results.json --out report.md
```

이 명령은 `qmtl.runtime.transforms.alpha_performance.alpha_performance_node` 를 사용해 표준 지표를 계산하고 마크다운 리포트로 저장합니다.

생성된 지표는 `alpha_performance.<metric>` 네임스페이스(예: `alpha_performance.sharpe`, `alpha_performance.max_drawdown`)로 출력되어 WorldService의 `alpha_metrics` 봉투와 일관되며, 알 수 없는 키는 무시되어 파서가 향후 진화해도 안전하게 유지됩니다.
