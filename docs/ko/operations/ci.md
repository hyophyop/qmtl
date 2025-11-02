# CI 환경

지속적 통합(CI)은 uv가 관리하는 가상환경에서 Python 3.11로 실행됩니다. 자원 누수를 조기에 발견하기 위해 테스트는 경고를 오류로 처리합니다.

- Python: 3.11 (`uv python install 3.11` + `uv venv`)
- 의존성 설치: `uv pip install -e .[dev]`
- Protobuf 생성: `uv run python -m grpc_tools.protoc ...`
- 테스트: `PYTHONPATH=qmtl/proto uv run pytest -W error -n auto -q tests`

병렬화는 `pytest-xdist` 를 사용하므로 CI 이미지에 설치되어 있어야 합니다. 권한 있는 구성은 `.github/workflows/ci.yml` 을 참고하세요.

## 행 탐지 프리플라이트

전체 테스트 전에 빠른 프리플라이트 단계를 추가해, 어떤 테스트도 잡을 행(Hang) 상태로 만들지 못하도록 합니다. `pytest-timeout` 과 `faulthandler` 를 활용해 장시간 실행 테스트가 트레이스백과 함께 실패하도록 합니다.

- 프리플라이트 명령(추가 설치 단계 불필요):

```
PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q \
  --timeout=60 --timeout-method=thread --maxfail=1
```

- 선택: 임포트/수집 건전성 확인

```
uv run -m pytest --collect-only -q
```

- 프리플라이트 이후 전체 테스트:

```
PYTHONPATH=qmtl/proto uv run pytest -W error -n auto -q tests
```

### GitHub Actions 예시

전체 테스트 단계 전 삽입 가능한 스니펫:

```
      - name: Preflight – import/collection
        run: uv run -m pytest --collect-only -q

      - name: Preflight – hang detection
        run: |
          PYTHONFAULTHANDLER=1 \
          uv run --with pytest-timeout -m pytest -q \
            --timeout=60 --timeout-method=thread --maxfail=1

      - name: Run tests (warnings are errors)
        run: PYTHONPATH=qmtl/proto uv run pytest -p no:unraisableexception -W error -q tests
```

### 작성자 가이드

- 60초를 legitimately 초과하는 테스트는 명시적 타임아웃을 설정하세요.

```
@pytest.mark.timeout(180)
def test_long_running_case():
    ...
```

- 오래 걸리거나 외부 리소스를 사용하는 테스트는 `slow` 로 표시하고 필요하면 프리플라이트에서 `-k 'not slow'` 로 제외합니다.
- 무제한 네트워크 대기를 피하고, 테스트 클라이언트에 항상 타임아웃을 지정하세요.

## 아키텍처 불변 조건(권장 검사)

핵심 불변 조건이 깨지면 즉시 실패하도록 가벼운 검사(단위/통합)를 추가하세요.

- GSG NodeID 고유성: 삽입된 노드 간 `node_id` 가 중복되지 않으며 BLAKE3 정규화를 통해 계산됩니다.
- 월드 로컬 격리: World A에서 `DecisionsRequest` 를 적용해도 World B 상태에 영향을 주지 않아야 합니다.
- EvalKey 무효화: `DatasetFingerprint`/`ContractID`/`CodeVersion` 혹은 `ResourcePolicy` 변경 시 새로운 `eval_key` 가 생성되고 재검증이 수행됩니다.
- DecisionsRequest 검증: 비거나 공백인 식별자는 거부되며, 중복은 저장 전 제거됩니다.
