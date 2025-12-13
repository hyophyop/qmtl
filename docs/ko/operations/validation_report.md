# Validation Report (표준 템플릿)

World Validation의 결과를 운영/리스크 관점에서 공유·보관하기 위해, `EvaluationRun`과 Model Card를 기반으로 **표준 Validation Report**를 생성합니다.

## 생성 방법

- 입력: EvaluationRun payload(JSON/YAML), Model Card payload(JSON/YAML)
- 출력: Markdown(`.md`)

예시:

```bash
uv run python scripts/generate_validation_report.py \
  --evaluation-run artifacts/evaluation_run.json \
  --model-card model_cards/my_strategy.json \
  --output validation_report.md
```

## 포함 내용(요약)

스크립트(`scripts/generate_validation_report.py`)가 생성하는 리포트는 아래 섹션을 포함합니다.

- Summary(상태/추천 스테이지/policy_version/ruleset_hash)
- Scope & Objective(모델 카드 기반)
- Rule outcomes(코어 + 확장 레이어 결과)
- Metrics snapshot(대표 메트릭 요약)
- Override 정보(존재 시)
- Limitations & recommendations(한계/권고사항)

## 관련

- Evaluation Store: `operations/evaluation_store.md`
- 운영 가시성(SLO/알람): `operations/world_validation_observability.md`

