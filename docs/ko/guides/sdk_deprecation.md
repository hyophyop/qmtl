# SDK ValidationPipeline 디프리케이션 가이드

SDK의 `ValidationPipeline`은 로컬 사전 점검(precheck) 용도로만 유지되고, 정책 평가/게이팅의 단일 출처(SSOT)는 WorldService 입니다. 이 가이드는 전환 플래그와 롤백 절차를 안내합니다.

## 기본 동작
- v1.5+: 환경변수 `QMTL_SDK_METRICS_ONLY=1`가 기본값이며, ValidationPipeline은 정책 게이팅을 건너뛰고 **metrics만 산출**합니다.
- WS 평가 결과가 최종 결정이며, SDK `precheck` 섹션은 참고용입니다.

## 플래그/롤백
- 비활성화(임시 롤백): `QMTL_SDK_METRICS_ONLY=0` (또는 false/no)로 설정하면 기존 SDK 게이팅 동작을 사용합니다.
- 문제 발생 시 플래그를 끄고 WS 평가/오케스트레이션만 신뢰하도록 설정을 유지합니다.

## 권장 사용
- 제출/테스트 파이프라인에서는 WS 결과(`SubmitResult.ws.*`)를 사용자에게 표준 출력으로 노출하고, `precheck`는 별도 섹션으로 분리합니다.
- SDK→WS 불일치가 있을 경우 WS 로그/메트릭을 우선 확인하고, `precheck`는 디버그 힌트로만 사용합니다.

## 추가 단계(예정)
- WS 단일 오케스트레이션 테스트(룰 실행/오류/오프로드)와 SDK 디프리케이션 알림을 순차적으로 배포합니다.
