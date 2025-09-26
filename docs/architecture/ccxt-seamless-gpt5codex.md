목표 및 제약 정리
QMTL의 Feature Artifact Plane은 데이터 스냅샷을 dataset_fingerprint로 고정하고 도메인 간 공유를 읽기 전용 아티팩트로 제한해 데이터 혼합을 방지합니다.
백테스트/드라이런 입력은 as_of 커밋을 반드시 명시해야 하며, WorldService의 결정 흐름과 결합된 ExecutionDomain·World 격리 모델을 따라야 합니다.
제안 아키텍처
거래소 수집 계층 (ccxt 어댑터)
ccxt 기반 커넥터를 데이터 수집 워커로 구성하고, 거래소/마켓 식별자를 표준 종목 메타데이터로 매핑하여 이후 Seamless 파이프라인이 이해할 수 있는 피드 명세(심볼, 인터벌, 거래소)를 생산합니다.
각 워커는 스냅샷 생성 시점에 dataset_fingerprint와 as_of를 계산해 메타데이터에 포함시켜 Feature Artifact Plane과 일관되게 유지합니다.
Seamless Data Provider 전처리 & 합성
ccxt 워커가 생성한 프레임을 Seamless Data Provider(SDP)에 전달해 정규화(스키마/시간 롤업), 품질 플래그 산출, 리포트 발행을 수행합니다. 이 단계에서 거래소별 미세한 컬럼 차이나 캔들 정렬 문제를 해결하고 완결된 메타데이터를 제공합니다.
ccxt 실시간 스트림과 히스토리 백필을 SDP가 동일 API로 노출하므로, 전략 노드에서는 항상 준비된 데이터처럼 소비할 수 있습니다.
백필·캐시 계층
Seamless의 분산 백필 코디네이터를 활성화하여(환경 변수 QMTL_SEAMLESS_COORDINATOR_URL) 거래소별 히스토리 갭을 자동으로 메우고, 중복 백필을 방지합니다. 실패 시 재처리 훅과 진행률 메트릭을 활용해 운영 가시성을 확보합니다.
백필된 데이터는 Feature Artifact 저장소(객체 스토리지, RocksDB 등)에 버전으로 보존해 도메인 격리를 유지합니다.
SLA·관찰성
Seamless의 SLA 정책을 활용해 저장소/백필/라이브 경로마다 시간 예산을 측정하고 초과 시 예외와 알림을 발생시킵니다. Prometheus 지표(seamless_sla_deadline_seconds, backfill_completion_ratio)와 로그로 파이프라인 상태를 상시 모니터링합니다.
WorldService 및 실행 도메인 연계
WorldService는 데이터 신선도(now - data_end ≤ max_lag)를 판단해 실행 모드를 결정하므로, Seamless가 생산한 품질/갭 메타데이터를 WorldService로 피드백하여 도메인 스위치나 주문 게이트 결정을 지원합니다.
Gateway는 world_id, execution_domain, as_of가 포함된 Compute Context를 세션마다 전달하므로, ccxt+SDP 파이프라인도 동일 메타데이터를 제공해 전략/월드 별 캐시 격리를 유지해야 합니다.
구현 로드맵
커넥터 패키지화
ccxt 어댑터를 모듈화하고, 거래소별 제한(속도·레이트리밋)을 구성 가능하게 설계합니다.
Seamless 어댑터 계층
ccxt 출력 → Seamless 입력 변환기(스키마 매퍼, 타임존 정규화)를 작성하고, 품질 리포트를 WorldService/운영 대시보드에 연결합니다.
데이터 퍼시스턴스
Feature Artifact 저장소와 백필 스케줄러를 구성하여 dataset_fingerprint 단위로 버전 관리합니다.
도메인 통합 및 게이팅
WorldService와 Gateway가 요구하는 컨텍스트 필드를 전달하고, 데이터 신선도에 따라 자동으로 compute-only 모드나 라이브 모드를 선택하도록 정책을 연결합니다.
관찰성·SLA 운영
Seamless 지표/로그를 통합 모니터링에 수집하고, SLA 위반 시 경보와 자동 강등 로직(예: 백테스트 모드)으로 연동합니다.
이 구조를 따르면 ccxt 수집과 Seamless Data Provider의 정합성 검증·백필 기능이 결합되어, 전략에서는 항상 준비된 고품질 거래소 데이터를 도메인 격리를 유지한 채 활용할 수 있습니다.