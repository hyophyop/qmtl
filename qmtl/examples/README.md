# QMTL Example Suite

이 디렉터리는 QMTL SDK 사용법을 보여 주는 예제 코드를 유형별로 정리한 것입니다.
각 예제는 `architecture.md` 문서의 설계를 따르며, 실전 전략 구현 시 참고용으로 활용할 수 있습니다.

예시 Gateway와 DAG manager 설정은 `qmtl.yml`에 포함되어 있습니다. 환경에 맞게 수정한 뒤
CLI 실행 시 `--config` 인자로 전달하세요.

## 구조

- `strategies/` - 다양한 전략 구현 예제
- `parallel/` - 멀티 스트래티지 실행 예제
- `metrics/` - 모니터링 및 메트릭 수집 예제
- `utils/` - 보조 도구와 설정 관련 스크립트

## 실행 예

예제는 다음과 같이 모듈 경로로 실행할 수 있습니다.

```bash
python -m qmtl.examples.strategies.general_strategy
python -m qmtl.examples.parallel.questdb_parallel_example
```

Ray 기반 병렬 실행을 사용하려면 다음과 같이 `--with-ray` 옵션을 추가하세요.

```bash
python -m qmtl.examples.strategies.general_strategy --with-ray
```

백테스트가 필요한 경우 `Runner.backtest()`에 시작/종료 타임스탬프를 지정하세요.
