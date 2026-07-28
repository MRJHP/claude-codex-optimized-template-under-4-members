# 개발 환경 (uv / ruff / mypy / pytest)

이 프로젝트는 [uv](https://docs.astral.sh/uv/)로 의존성과 가상환경을 관리한다. `pip install`, `python -m venv`를
직접 쓰지 않는다.

## 자주 쓰는 명령

```bash
uv sync                       # pyproject.toml 기준으로 의존성 설치/동기화
uv add <package>              # 런타임 의존성 추가
uv add --dev <package>        # 개발 의존성 추가 (dependency-groups.dev)
uv run pytest                 # 테스트 실행 (커버리지 포함, pyproject.toml 설정)
uv run pytest tests/test_x.py -k name  # 특정 테스트만 실행
uv run ruff check .           # 린트
uv run ruff check . --fix     # 자동 수정 가능한 린트 문제 해결
uv run ruff format .          # 포맷팅
uv run mypy .                 # 타입 체크 (strict 모드)
```

## 커밋 전 체크리스트

1. `uv run ruff check . --fix && uv run ruff format .`
2. `uv run mypy .`
3. `uv run pytest`

세 명령이 모두 통과하지 않으면 커밋하지 않는다. 실패 시 원인을 분석하고, 반복해서 막히면
[codex-delegation.md](codex-delegation.md) 기준에 따라 Codex 상담을 고려한다.

## pre-commit

`.pre-commit-config.yaml`에 ruff check/format, mypy가 로컬 hook으로 등록되어 있다. 최초 1회 설치한다:

```bash
uv run pre-commit install
```

이후 `git commit` 시 자동으로 실행된다. pytest는 속도 문제로 pre-commit에 포함하지 않고 CI
(`.github/workflows/ci.yml`)에서 실행한다.

### Windows + 저장소 경로에 한글(비 ASCII)이 포함된 경우 주의

Windows에서 `uv run pre-commit install`을 실행하면, 저장소 경로에 한글 등 비 ASCII 문자가 있을 때
`.git/hooks/pre-commit` 스크립트에 그 경로를 **UTF-8이 아닌 시스템 로케일(CP949 등)** 로 잘못 인코딩해서
쓰는 경우가 있다. Git Bash는 hook 스크립트를 UTF-8로 해석하므로 `INSTALL_PYTHON` 경로가 실제 `.venv`
경로와 바이트 단위로 어긋나고, 그 결과 `` `pre-commit` not found. Did you forget to activate your
virtualenv? `` 에러와 함께 `git commit`이 실패한다.

**해결**: hook을 재설치할 때 `PYTHONUTF8=1`을 명시해서 UTF-8로 강제 기록한다.

```bash
PYTHONUTF8=1 uv run pre-commit install --overwrite
```

한 번만 다시 설치하면 되고, 이후 `git commit`은 평소처럼 동작한다.
