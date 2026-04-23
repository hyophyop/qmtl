# World Isolation Runtime Scope

월드 격리 후속 작업에서 남아 있던 운영 갭은 "누가 쓰기를 허용받는가"와 "로컬 쓰기 경로가 어떤 스코프로 분리되는가"를 일치시키는 데 있다. 이 문서는 기존 아키텍처 계약을 다시 정의하지 않고, 운영자가 실제 배포/백테스트 환경에서 확인해야 할 RBAC·write-scope·경로 네임스페이스 점검 항목만 정리한다.

관련 규범 문서:

- [Architecture & World ID Flow](../architecture/architecture.md)
- [WorldService](../architecture/worldservice.md)
- [Configuration Reference](../reference/configuration.md)

## 1. 권한과 쓰기 소유권

- WorldService가 월드 범위 RBAC와 쓰기 감사의 권위이다. `apply`, `activation PUT`, 월드 상태 변경은 WorldService operator 권한으로만 허용한다.
- Gateway는 프록시/브리지 역할만 수행한다. Gateway 또는 SDK 로컬 설정으로 write-scope 를 우회해선 안 된다.
- `live`/`shadow` 는 mutable runtime state 를 공유하거나 새 로컬 artifact/cache 를 기록하는 경로로 사용하지 않는다. cross-domain 재사용은 기존 계약대로 immutable feature artifact 의 read-only 소비에 한정한다.

## 2. backtest/dryrun 로컬 저장소 정책

- `backtest`/`dryrun` 에서 로컬 write 가 필요한 경로는 반드시 `world_id` 와 `execution_domain` 으로 namespaced 되어야 한다.
- 기본값 또는 상대 경로를 사용할 때는 장기 공유 디렉터리를 재사용하지 않고 임시 루트(`$TMPDIR/qmtl/...`) 아래로 이동시켜야 한다.
- 절대 경로를 명시적으로 설정한 경우에도 실제 쓰기 경로는 `world=<id>/execution_domain=<domain>` 하위로 분리해야 한다.
- 적용 대상:
  - `seamless.artifact_dir`
  - `cache.feature_artifact_dir`
  - `cache.tagquery_cache_path`

## 3. 큐 / 캐시 / 아티팩트 네임스페이스 체크리스트

- 큐 토픽: 프로덕션 토픽은 `{world_id}.{execution_domain}.<topic>` 형태를 유지해야 한다.
  - 회귀 가드: `tests/qmtl/services/dagmanager/test_topic_namespace.py`
- feature artifact write-scope: `cache.feature_artifact_write_domains` 로 `backtest`/`dryrun` 만 쓰기를 허용하고, `live`/`shadow` 는 read-only 소비로 유지한다.
  - 회귀 가드: `tests/qmtl/runtime/sdk/test_feature_artifact_plane.py`
- TagQuery 로컬 캐시: 백테스트/드라이런에서 world/domain 분리 경로를 사용하고, 상대/기본 경로는 임시 루트로 내려가야 한다.
  - 회귀 가드: `tests/qmtl/runtime/sdk/tagquery/test_cache_parity.py`
- Seamless artifact manifest: producer provenance 에 `world_id`, `execution_domain`, `strategy_id` 가 남아야 한다.
  - 회귀 가드: `tests/qmtl/runtime/sdk/test_artifact_registrar.py`

## 4. 운영 승인 전 최소 점검

- 월드 쓰기 API 가 WorldService RBAC 경계 뒤에만 있는지 확인한다.
- 로컬 backtest/dryrun 실행에서 생성된 cache/artifact 경로가 `world=<id>/execution_domain=<domain>` 로 분리되는지 확인한다.
- 운영 설정이 상대 경로나 홈 디렉터리 기본값에 의존할 때, 실제 write target 이 임시 루트로 강등되는지 확인한다.
- queue namespace, feature artifact write-domain, manifest provenance 회귀 테스트를 함께 통과시킨다.
