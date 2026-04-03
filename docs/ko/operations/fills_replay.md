# Fill Replay 런북

이 문서는 왜 fill replay가 현재 Gateway의 공개 표면에서 제외되어 있는지 기록한다.

## 보안

`/fills` 엔드포인트는 공유 HMAC 시크릿으로 서명된 Bearer 토큰을 요구한다. 토큰에는 요청 범위를 제한하는 `world_id`, `strategy_id` 클레임이 포함되어야 한다.

## 현재 동작

현재 빌드는 `GET /fills/replay`를 노출하지 않는다. replay 전달은 아직 지원되는 공개 계약이 아니므로, 부분 구현을 노출하는 대신 placeholder 라우트를 제거했다.

## 향후 구현 메모

replay 전달이 구현되면 이 런북은 최종 요청 계약, 보안 모델, 운영 검증 절차를 반영하도록 갱신되어야 한다.
