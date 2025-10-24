# Report CLI

`qmtl report` 명령은 `returns` 배열을 포함하는 JSON 파일로부터 간단한 성과 리포트를 생성합니다.

```bash
qmtl report --from results.json --out report.md
```

이 명령은 `qmtl.runtime.transforms.alpha_performance.alpha_performance_node` 를 사용해 표준 지표를 계산하고 마크다운 리포트로 저장합니다.
