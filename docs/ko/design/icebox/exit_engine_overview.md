---
title: "Exit Engine 개요 (초안)"
tags: [design, exit, risk, signals]
author: "QMTL Team"
last_modified: 2025-12-15
status: draft
---

{{ nav_links() }}

# Exit Engine 개요 (초안)

!!! warning "Icebox (참고용, 현재 작업 대상 아님)"
    이 문서는 `docs/ko/design/icebox/`에 보관된 참고용 설계 스케치입니다. **현재 작업 대상(SSOT)** 이 아니며, 필요 시 배경/아이디어 참고로만 사용하세요. 채택한 내용은 `docs/ko/architecture/` 또는 코드/테스트로 승격해 반영합니다.

!!! abstract "목적"
    이 문서는 **전략 진입 신호와 별개로 리스크 기반 추가 Exit 신호**를 생성하는 `Exit Engine`의 목적과 역할을 개략적으로 정의한다.  
    구현/연결은 `risk_signal_hub`가 안정화된 이후 진행하며, 현 단계에서는 **목적과 인터페이스 방향성**만을 공유한다.

관련 문서:
- World 검증 계층 설계: [world_validation_architecture.md](world_validation_architecture.md)
- 모델 리스크 관리 프레임워크: [model_risk_management_framework.md](model_risk_management_framework.md)
- Risk Signal Hub 아키텍처(정리본): [architecture/risk_signal_hub.md](../../architecture/risk_signal_hub.md)

---

## 0. 목적과 비범위

- 목적: 시장 상태, 리스크 한계, 이론적 제약을 근거로 **전략의 내부 exit 신호와 독립적인 추가 exit/감축 신호**를 생성해, 과도한 손실/리스크 노출을 사전에 완화한다.
- 비범위: 전략 자체의 진입/익절/손절 로직 변경, 실행/체결 엔진 구현, 신규 리스크 모델 개발(별도 리스크 엔진 문서 참조).

---

## 1. 역할 정의 (초안)

- 입력: `risk_signal_hub`가 제공하는 포트폴리오 스냅샷(가중치, 공분산/상관, 실현 리턴), 시장/마켓 스냅샷, 사전 정의된 리스크 규칙 세트.
- 처리: 규칙 기반(or 모델 기반)으로 **추가 exit/감축** 신호 계산 (예: VaR/ES 초과, 스트레스 DD 초과, 시장 구조 붕괴 지표 감지).
- 출력: 예: `exit_signal_emitted` 이벤트(전략별/월드별 exit 권고, 감축 비율, 사유/지표 포함)를 발행하여 gateway/WS가 소비할 수 있도록 한다.
- 속성: 읽기 전용 소비자이며, 포지션 변경/체결은 gateway가 수행한다.

---

## 2. 데이터 연결 (risk_signal_hub 기반)

- **소스**: `risk_signal_hub`의 스냅샷/이벤트(예: ControlBus `risk_snapshot_updated`).
- **소비**: Exit Engine은 hub를 통해 필요한 지표만 읽고, 추가로 시장/마켓 지표(예: VIX, 스프레드, 유동성 지표)를 참조한다.
- **배포**: 결과 신호는 예: `exit_signal_emitted` 이벤트로 발행하여 gateway/WS가 적용/검증할 수 있게 한다. 적용 우선순위/충돌 정책은 별도 운영 문서에서 정의.

---

## 3. 향후 계획 (연결 시점에 조정)

1. Hub 계약 확정 후, Exit Engine 입력 스키마 정의 (필수: weights, covariance/상관, as_of; 선택: stress 결과, realized returns ref).
2. 규칙 세트 초안: VaR/ES 한계 초과, 스트레스 DD 초과, 마켓 스트럭처 붕괴 지표, 롤링 유동성 악화 등.
3. 이벤트 통합: ControlBus/Kafka로 ExitSignal 발행 → gateway 적용/WS 로그.
4. 운영 가드: 신호 우선순위, 승인/override 경로, 감사 로그(신호 근거 지표 포함).

---

## 4. 참고

- 구현/스케줄링: risk_signal_hub 이벤트를 트리거로 백그라운드 워커에서 실행(동기 WS/SDK 변경 없음).
- 보안/권한: exit 신호는 읽기/발행 권한을 분리하고, 포지션 변경은 gateway에서만 허용.

{{ nav_links() }}
