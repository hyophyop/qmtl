아키텍처 문서를 훑어보면 “**SDK는 단순**, 백엔드는 **전역 재사용과 결정(activation) 통제**”라는 목표는 잘 잡혀 있습니다. 다만 *“전역 DAG에서 각 노드는 하나만 돌도록 보장”* 과 *“부분 DAG 제출을 통한 최대 재사용”* 을 **운영 관점에서 실제로 보장**하려면 몇 가지 결정적 공백과 리스크가 남아 있습니다. 아래는 **우선순위(P0/P1/P2)** 로 정리한 개선 제안과, 각 제안의 *의도 → 변경 사항 → 구현 힌트 → 검증 기준(수용 조건)* 입니다. 필요 시 업계 de‑facto 패턴(Streams/CEP, Bazel/Nix, CloudEvents/Schema Registry, Flink/Kafka exactly‑once 등)을 교차 인용해 폭을 넓혔습니다.

---

## TL;DR — 바로 적용할 P0 (신뢰성/결정성/단일 실행 보장)

1. **전역 “단일 실행(once‑and‑only‑once per Node×Time)” 보장층 추가**

* **의도:** 현재는 SDK가 로컬에서 실행합니다. 동일 NodeID를 서로 다른 전략이 공유할 때 *“정말로 한 번만”* 실행되는지는 **중앙 조정/리스 체계** 없이는 우연에 맡겨집니다.
* **변경:** “계산 오너십(ownership)”을 *데이터·시간 버킷 기준*으로 분할하고, **소비자 그룹 파티션(assigner)** 또는 **리스 기반 리더십**으로 *한 시점의 한 노드*를 하나의 워커가 전담.
* **구현 힌트:**

  * `NodeID ⨉ interval ⨉ time_bucket`을 **파티션 키**로 삼아 Kafka 파티션(또는 Redpanda) → **컨슈머 그룹 1개만 실행**되게 배치.
  * 보조로 **임대(lease)**: `LEASE:{node_id}:{bucket}`를 etcd/Consul/Postgres advisory lock으로 𝑇초 갱신(renew)하며 소유권 부여. Redis Redlock은 분산락 안전성 논쟁이 있으므로 피하고(테스트 목적 외) **Kafka 파티션 + DB‑락** 조합 권장.
  * 산출물 커밋은 **트랜잭셔널 프로듀서**(Kafka idempotent producer + transactions)로 “**커밋 로그(예: node‑commit‑log, compacted 토픽)**”에 기록. Downstream은 커밋 로그를 근거로 중복 제거.
* **수용 기준:** 동일 Node×Bucket에 대해 병렬 워커 2개를 인위적으로 띄웠을 때 산출물이 정확히 1번만 커밋되고, 중복 산출물 0건(`commit_duplicate_total=0`).

2. **이벤트‑타임 워터마크 & 지연 허용(lateness) 모델 도입**

* **의도:** 다중 업스트림/다중 인터벌에서 **지연·역행 데이터**가 필연적으로 발생합니다. 현재 4‑D Tensor 모델은 정렬/충분도는 명시했지만 “**언제 fn(view)를 트리거**할지”의 **시간 의미론(event‑time)**, 워터마크, 허용 지연(allowed lateness)이 없습니다.
* **변경:** `NodeCache`가 **워터마크**(예: `wm = min(last_ts(u,i)) - L`)를 유지하고, `wm` 도달 시점에만 `compute_fn` 트리거. 늦게 온 바(캔들)는 “수정 이벤트(retract/upsert)”로 재계산 경로 명시.
* **구현 힌트:**

  * `compute_fn(view, watermark)` 시그니처(혹은 View 메서드)로 워터마크 노출.
  * `on_late` 정책(`ignore|recompute|side_output`)을 노드별로 설정.
* **수용 기준:** 역행 데이터 주입 테스트에서 (a) 지정 허용 지연 이내 → 정상 재계산, (b) 초과 → 설정에 맞춰 무시/측면 출력(side output)으로 분리.

3. **런타임 지문(runtime fingerprint) 포함한 재사용 경계 설정**

* **의도:** NodeID를 `(node_type, code_hash, config_hash, schema_hash)`로 정의했지만, **BLAS/FMA, NumPy/Pandas, Python minor 버전, OS/CPU 아키텍처** 차이는 **수치 비결정성**을 유발합니다. 동일 ID 재사용이 **숫자 드리프트**를 낳을 수 있음.
* **변경:** `runtime_fingerprint`(예: `python=3.11.x; numpy=1.26.x; qmtl=…; cpu=avx2; os=…; libc=…`)를 별도 필드로 관리하고 **재사용 정책**을 선언:

  * 기본: `runtime_compat=loose`(미세 차이 허용)
  * 엄격: `runtime_compat=strict`(fingerprint mismatch → **재사용 금지**)
* **구현 힌트:** Bazel/Nix의 content‑addressable 개념 차용. Fingerprint는 NodeID에는 넣지 말고 **재사용 판단과 캐시 스코프**에 사용(그래프 폭발 방지).
* **수용 기준:** 동일 코드이지만 NumPy 버전만 다른 환경을 혼합 배포 시 `strict` 모드에서는 재사용이 차단되고, `loose` 모드에서는 허용되며 수치 허용오차 내에 수렴.

4. **프리‑웜업(warmup) 단축: 스냅샷 체크포인트 + 상태 하이드레이션**

* **의도:** interval×period 조건 때문에 실시간 전환/장애 복구에 **긴 웜업 시간**이 발생.
* **변경:** `NodeCache`를 \*\*주기 스냅샷(Parquet/Arrow + 인덱스)\*\*으로 S3/MinIO에 적재, 재기동 시 **최근 스냅샷 하이드레이션**으로 웜업 시간 단축.
* **구현 힌트:**

  * 스냅샷 키: `(node_id, interval, wm_ts, schema_fingerprint, runtime_fingerprint)`
  * 적용 전 **state\_hash** 일치 여부 점검(불일치 시 버림).
* **수용 기준:** 웜업 30분 필요 노드가 재배포 후 **N분 → N/10 이하**로 단축(목표). 스냅샷 손상/불일치 시 자동 폴백.

5. **Schema Registry & CloudEvents(Proto) 이중화**

* **의도:** JSON‑only는 스키마 호환성·진화 관리에 취약. 문서에 CloudEvents 도입은 있으나(미정), *실무적으로* **버전 호환**과 **경량 인코딩**이 필요.
* **변경:**

  * 데이터 토픽: **Avro/Proto + Schema Registry**(compatibility = backward/forward 선택)
  * 컨트롤 토픽(ControlBus): **CloudEvents‑over‑Protobuf**(JSON은 외부/디버그용)
* **구현 힌트:** Kafka 헤더에 `schema_id`를 넣고, `QueueUpdated/ActivationUpdated`에 **monotonic seq**와 **state\_hash** 추가.
* **수용 기준:** minor/breaking 변경 테스트에서 **자동 호환 판정 & 롤링 업그레이드**, 역직렬화 오류율 0.

---

## P1 — 강한 재현성/캐시·리소스 최적화/운영성

6. **“콘텐츠 지향 캐시(Content‑Addressed Compute)” 채택**

* **의도:** 동일 입력 윈도우·동일 코드면 결과가 동일해야 합니다. 이를 **키로 직접 보장**하면 전역 재사용이 강력해집니다.
* **변경:** 각 노드 출력 청크를 `(NodeID, input_window_hash, params_hash)`로 **CAS** 저장. input\_window\_hash는 **업스트림 큐 슬라이스들의 Merkle root**.
* **구현 힌트:** Bazel Remote Cache/Materialize 원리 차용. Arrow RecordBatch 단위로 저장하고 지문은 BLAKE3(속도) + SHA‑256(감시) 이중 표기.
* **수용 기준:** 동일 윈도우 반복 계산 시 **캐시 히트율↑**, 실제 계산 회피율과 지연 단축 확인.

7. **TagQuery의 불안정성(의도된 동작) 제어: ‘핀셋 고정(토글)’ + 고급 질의**

* **의도:** 태그 기반 자동 확장은 기본적으로 “동적(Dynamic)”으로 흔들릴 수 있게 설계된 **의도된 동작**입니다. 다만 운영 시점에 따라 **안정성(고정된 입력 집합)** 이 필요한 구간이 있어, **핀셋 고정 기능을 켜고/끄는 토글**을 제공합니다.
* **변경:**

  * 질의 언어: `match_mode`(any/all)에서 **부울식**(예: `(asset in {BTC,ETH}) AND price AND interval=60s`)로 확장.
  * **핀셋 고정(pinned selection, 토글 가능)**:
    - `selection_mode = dynamic | pinned` (기본값: `dynamic`).
    - `pinned` 모드에서는 “핀셋 시점의 실체화 집합”을 `etag`로 고정하고, 수동 `refresh()` 또는 주기 `resync_interval`로만 갱신.
    - 변경 폭 제한: `max_delta_per_resync`(추가/삭제 허용 최대치), 변화 발생 시 `cooldown_after_change` 동안 재고정 유예.
* **구현 힌트:**
  * `TagQueryNode(query_tags, interval, period, selection_mode=..., pinned_etag=optional)` 옵션 추가.
  * `TagQueryManager`가 `resync_interval`, `cooldown_after_change`, `max_delta_per_resync`를 관리하고, `pin()/unpin()/refresh()` API 제공.
  * 고정 세트는 UI/로그에서 `etag`와 함께 노출해 운영자가 시점을 식별 가능하게.
* **수용 기준:**
  * `selection_mode=dynamic`에서 새 큐 등장/태그 변경 시 즉시(또는 사양된 정책에 따라) 반영.
  * `selection_mode=pinned`에서 동일 상황에도 입력 집합 불변 유지; `refresh()` 또는 `resync_interval` 도달 시에만 변화. 변화 폭은 `max_delta_per_resync` 이하이며 초과 시 경고/보류 처리.
  * 토글 전환 시(동적↔핀셋) 캐시 드랍/웜업 정책이 문서된 절차대로 안전 수행.

8. **Gateway 큐·락 계층 재검토(“Redis 의존” 최소화)**

* **의도:** Redis AOF 유실·분할(brain split) 리스크는 문서에서도 비관 시나리오로 언급.
* **변경:**

  * **작업 큐/락**은 Kafka 파티션·Postgres advisory lock으로 이동(또는 etcd).
  * Redis는 **캐시/세션**으로 축소.
* **구현 힌트:** Ingest FIFO→Kafka(주문형 파티션), FSM은 Postgres row‑level with `SKIP LOCKED`.
* **수용 기준:** Redis 장애 주입 시에도 **제출/디퓨전(diff)·락**이 중단되지 않음.

9. **수치 결정성 가이드라인(엔지니어링 표준)**

* **의도:** 동일 입력인데 re-run 값 차이 줄이기.
* **변경:** 표준 운영 옵션: `OMP_NUM_THREADS=1`(필요 시), `MKL_CBWR=COMPATIBLE`, `numpy` “매든” 설정, 랜덤 시드·dtype 통일(float64/32 결정), FMA 금지/허용 정책.
* **구현 힌트:** `Runner`가 실행 전 환경 정규화 로그를 남기고 hash에 포함.
* **수용 기준:** **재현성 테스트**(N회 반복)에서 허용 오차 내 수렴.

10. **Observability 일원화: Trace/Metric/Log 상관관계 키**

* **의도:** 현재 correlation\_id 언급은 산발적. 전 경로에 **W3C traceparent**를 전파해 원스톱 분석 가능하게.
* **변경:** SDK→Gateway→DAGM/WS→ControlBus로 **trace context 전파**, OpenTelemetry 자동 계측.
* **구현 힌트:** 첫 Submit 시 `trace_id` 고정, 모든 컨트롤 이벤트에 헤더/필드로 삽입.
* **수용 기준:** 단일 전략 실행을 **하나의 트레이스 그래프**로 관측 가능, p95 병목 지점 파악.

11. **WorldService 결정 TTL의 적응화(Adaptive TTL)**

* **의도:** 고빈도/저지연 세계에 300s 고정 TTL은 둔감.
* **변경:** world별 **SLO 기반 TTL**: 데이터 통화성(data currency)·신뢰 신호를 기반으로 TTL 자동 조정(예: 60–600s 범위).
* **수용 기준:** 데이터 지연 증가 시 TTL 자동 단축으로 stale 의사결정 윈도우 감소.

12. **ControlBus 신뢰성 보강: 스냅샷/시퀀스/재동기화**

* **의도:** at‑least‑once + etag만으로는 결손 탐지가 늦을 수 있음.
* **변경:** `seq_no(per world/tags)`, 첫 메시지 **풀 스냅샷 or state\_hash**, 간극 감지 시 Gateway가 *자동 HTTP 재조회*.
* **수용 기준:** 인위적 메시지 드롭에서도 SDK 상태가 HTTP 재동기화로 **최대 1 주기 내** 회복.

---

## P2 — 전략 DSL·개발자 경험/보안

13. **DSL 정교화: 타입 안정·컴파일 타임 검증·SSA IR 고도화**

* **의도:** YAML/파이썬 DSL 혼용에서 **사전 오류 검출** 극대화.
* **변경:**

  * interval/period 타입 엄격화(`Duration`), 태그 부울식, `compute_fn` 시그니처 검사.
  * SSA IR에 **정적 데이터 의존·사이드 이펙트 탐지** 룰 추가(네트워크/파일 접근 금지).
* **수용 기준:** CI에서 전략 제출 전 오류 클래스 감지율↑, 런타임 실패율↓

14. **CAS 서명 및 자산 무결성**

* **의도:** 모델/파라미터/코드 아티팩트 서명·검증.
* **변경:** Artifact에 **공개키 서명**(cosign류) + 실행 전 검증.
* **수용 기준:** 변조 자산 실행 차단, Audit 로그에 서명 체인 남김.

15. **권고: BLAKE3(속도) + SHA‑256(호환) 이중 해시**

* **의도:** NodeID 해시는 SHA‑256 유지(충돌 우려 거의 없음). 다만 **대량 해시** 경로엔 BLAKE3가 유리.
* **변경:** NodeID는 현행 유지, 대용량 입력 윈도우/스냅샷 지문은 **BLAKE3(primary)** + SHA‑256(감시).
* **수용 기준:** 해시 비용↓, 스루풋↑, 보안·감사 요구 충족.

16. **테스트 전략: 쉐도잉/카나리아 검증의 자동화**

* **의도:** VersionSentinel 트래픽 스플릿은 훌륭하나, **지표 드리프트** 자동 감시 필요.
* **변경:** “shadow compute” 모드(신/구 결과의 Δ, 상관, 히스토그램 비교)와 **3단계 Gating**: p95 Δ < ε → 10% → 50% → 100%.
* **수용 기준:** 프로모션 실패 시 자동 롤백, Δ·히스테리시스 규칙 준수.

---

## 극단적(비관) 장애 시나리오 3종과 대응

1. **DAG Manager/Neo4j 조각화 + 큐 메타 불일치**

* **효과:** 새 전략이 오래된 큐로 라우팅 → 데이터 불일치.
* **대응:** `state_hash` 불일치 → Gateway가 **강제 풀 스냅샷**+읽기전용 모드 진입, 컨트롤 이벤트만 재수신할 때까지 live 차단.

2. **ControlBus 대규모 지연/역행**

* **효과:** Activation 업데이트 손실·순서 뒤바뀜.
* **대응:** seq/etag 기반 **간극 감지 → HTTP 리컨사일**. ActivationEnvelope는 **모노토닉 etag/run\_id** 비교로 idempotent.

3. **CAS 스냅샷 손상/롱테일 지연**

* **효과:** 재기동 후 웜업 복귀 실패.
* **대응:** 다중 리비전 보관 + Checksum 이중화(BLAKE3/SHA256), 실패 시 자동 웜업 폴백 경로, 알람 규칙(“warmup\_exceeded\_seconds”).

---

## 문서 자체 개선(작지만 효과 큰 정리)

* **중복 서술 정리:** `Backtest Mode` 항목에 동일 문장 반복이 있습니다(가독성·정합성 차원에서 정리 권장).
* **용어 일관화:** `match_mode` 표기를 일관되게 사용.
* **정상/지연/역행 타임라인 도식** 추가: 워터마크/지연 처리/재계산 경로를 하나의 시퀀스 다이어그램으로.

---

## “왜 이게 목적 달성에 직결되는가?”

* **단일 실행 보장층(P0‑1)** 없이는 “전역 한 번 실행”이 문서적 약속에 머뭅니다. 파티션/리스 기반 오너십 + 트랜잭셔널 커밋은 업계 표준(Streams/Flink/Kafka)로, **중복/경합을 구조적으로 제거**합니다.
* **이벤트‑타임/워터마크(P0‑2)** 는 다중 업스트림/다중 인터벌 합성의 *이론적 필수조건*입니다. 이게 없으면 지연/역행 데이터에 취약합니다.
* **런타임 지문(P0‑3)** 과 **스냅샷 하이드레이션(P0‑4)** 은 재사용성과 가동성의 실전 보강입니다. “같은 코드면 같은 결과”를 시스템적으로 근사하고, 배포/장애 시 **시간의 비용**을 줄입니다.
* **Schema Registry + Proto CloudEvents(P0‑5)** 는 *성장 후 고통*을 선제 차단합니다. 컨트롤/데이터 평면 각각에 맞는 표준을 쓰면 **장기 호환성과 성능**이 확보됩니다.

---

## 단계별 적용 로드맵(제안)

* **Wave‑1 (2–4주):**

  * 파티셔닝 키 정의(Node×Bucket), 임대/락 PoC, 커밋 로그(compacted) 도입
  * 워터마크·lateness 정책 및 SDK/Runner 시그니처 확정
  * Observability(Trace context) 전파 기본선
* **Wave‑2 (4–6주):**

  * Snapshot 하이드레이션/ CAS 저장소(Arrow/Parquet)
  * Schema Registry 연결 및 ControlBus Proto 이행
  * TagQuery 핀셋 고정 + 쿨다운 정책
* **Wave‑3 (6–10주):**

  * runtime\_fingerprint 정책/옵션화, 수치 결정성 가이드 배포
  * 권한/서명 체계, Shadow compute 카나리아 자동화
  * Redis 의존 축소(큐/락을 Kafka/DB로 이관)

---

필요하면 위 제안 중 **P0‑1(단일 실행 보장층)** 과 **P0‑2(워터마크 의미론)** 부터 바로 작동하는 **참조 구현 스니펫**(파티션 키 계산, 임대 핸들러, 워터마크 트리거러)을 만들어 드리겠습니다.
