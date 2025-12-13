# Independent Validation 운영 모델

이 문서는 [World 검증 계층 설계](../design/world_validation_architecture.md) §5.3(운영·거버넌스)에서 제안한 **독립 검증(Independent Validation)** 을 실제 저장소/CI 운영 관점에서 재현 가능하도록 정리합니다.

## 목적

- “전략 코드” 변경과 “검증 룰/정책” 변경의 **소유권/승인 경계**를 명확히 합니다.
- 검증 룰/정책 변경 시 **회귀 영향(impact) 리포트**를 CI에서 생성하고, 임계 초과 시 실패하도록 합니다.
- 승인·변경 로그를 최소 포맷으로 남겨 재현성을 확보합니다.

## 권한 모델(RACI)

- **Quant(전략)**: 전략 코드 변경 주도, 검증 실패 케이스 제보/재현 지원
- **Validation/Risk(독립 검증)**: 검증 룰/정책 변경의 승인(merge) 책임, 임계/override 정책 결정
- **Platform/Infra**: CI/스케줄 잡 운영, 아티팩트 보존/접근성 유지

권장 SLA(기본):

- 정책/룰 변경 PR: 1영업일 내 1차 리뷰, 2영업일 내 승인/반려 결정

## 저장소 경계(CODEOWNERS)

아래 경로는 “검증 룰/정책” 경계로 간주하며, CODEOWNERS 지정 리뷰어의 승인을 요구하도록 운영합니다.

- `docs/**/world/sample_policy.yml`
- `qmtl/services/worldservice/policy_engine.py`
- `qmtl/services/worldservice/validation_*.py`
- `qmtl/services/worldservice/extended_validation_worker.py`
- `scripts/policy_*.py`
- `operations/policy_diff/**`

설정 파일:

- `.github/CODEOWNERS`

!!! note "중요"
    CODEOWNERS 기반 “승인 없으면 merge 불가”는 GitHub의 브랜치 보호/룰셋 기능이 **활성화되어야** 강제됩니다.  
    개인 계정의 Private 저장소에서는 플랜 제약으로 일부 보호 기능이 비활성일 수 있으므로, 필요 시 저장소 공개 또는 플랜/조직 이전을 검토합니다.

## CI 강제(정책/룰 회귀 리포트)

정책/룰 경계 파일이 변경되면, 아래 워크플로가 자동 실행되어 **base vs head** 회귀 영향을 계산합니다.

- `.github/workflows/policy-diff-regression.yml`

기본 시나리오 세트:

- `operations/policy_diff/bad_strategies_runs/*.json`

산출물(artifact):

- base/head 스냅샷
- diff 리포트(JSON/Markdown)

임계 초과 시 실패(기본값 5%):

- `fail_impact_ratio` (0~1)

## 변경 로그(최소 포맷)

검증 룰/정책 변경 PR에는 아래를 PR 본문에 포함하는 것을 권장합니다.

- 변경 요약(룰/정책/메트릭)
- 영향 범위(impact ratio, affected 전략 수)
- 운영 조치(경고→실패 승격 여부, override/롤백 플랜)

## 로컬 리허설

정책/룰 변경 전후의 회귀 영향을 로컬에서 빠르게 확인할 수 있습니다.

```bash
uv run python scripts/policy_snapshot.py \
  --policy docs/ko/world/sample_policy.yml \
  --runs-dir operations/policy_diff/bad_strategies_runs \
  --stage backtest \
  --output head_snapshot.json

uv run python scripts/policy_snapshot_diff.py \
  --old base_snapshot.json \
  --new head_snapshot.json \
  --fail-impact-ratio 0.05 \
  --output policy_regression_report.json \
  --output-md policy_regression_report.md
```

`base_snapshot.json` 은 비교 대상 커밋(예: `main`)에서 동일 명령으로 생성합니다.
