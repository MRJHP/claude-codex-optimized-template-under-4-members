---
name: init
description: 이 템플릿을 새 프로젝트로 초기화한다 (uv 프로젝트 생성, 디렉토리 구조, 초기 설정). "프로젝트 초기화해줘", "새 저장소 세팅해줘" 같은 요청에 사용한다.
---

# init

이 저장소 자체가 재사용 템플릿이다. 새 실제 프로젝트를 시작할 때 이 스킬로 초기화한다.

## 절차

1. **README.md 생성**: `pyproject.toml`이 `readme = "README.md"`를 참조하므로 없으면 `uv sync`가 실패한다.
   최소한 프로젝트 한 줄 설명이라도 채운 `README.md`를 만든다.
2. **예제 코드 교체**: 템플릿에는 `uv run pytest`가 바로 동작하도록 최소 예제(`src/project/__init__.py`의
   `greet` 함수, `tests/test_project.py`)가 포함되어 있다. 이 예제를 실제 패키지 이름(`src/<package_name>/`)과
   실제 코드/테스트로 교체하거나 삭제한다. `pyproject.toml`의 `[project].name`도 실제 프로젝트 이름으로 바꾼다.
3. **의존성 초기화**
   ```bash
   uv sync
   uv run pre-commit install   # .pre-commit-config.yaml의 ruff/mypy hook 활성화
   ```
4. **git 초기화** (아직 git 저장소가 아니라면 사용자에게 확인 후 `git init`).
5. **CLAUDE.md / AGENTS.md 커스터마이즈**: `CLAUDE.md`의 프로젝트 개요를 실제 프로젝트에 맞게 채우고,
   `.codex/AGENTS.md`도 동일하게 갱신한다.
6. **DESIGN.md 개요 작성**: [.claude/docs/DESIGN.md](../../docs/DESIGN.md)의 "개요" 섹션을 채운다.
7. **환경 변수**: 실제로 필요한 키가 있으면 `.env.example`에 채우고, `cp .env.example .env` 후 실제 값을 넣는다
   (`.env`는 `.gitignore`에 이미 포함되어 커밋되지 않는다).
8. **첫 검증**: `uv run ruff check .`, `uv run mypy .`, `uv run pytest`가 통과하는지 확인한다
   ([dev-environment.md](../../rules/dev-environment.md)).

## 체크리스트

- [ ] README.md 생성 후 `uv sync` 성공
- [ ] `pre-commit install` 완료
- [ ] `pyproject.toml`의 프로젝트명/설명 갱신
- [ ] `src/project`, `tests/test_project.py` 예제를 실제 패키지/테스트로 교체 (남아있지 않은지 확인)
- [ ] CLAUDE.md, `.codex/AGENTS.md`에 실제 프로젝트 설명 반영
- [ ] `LICENSE`의 저작권자/연도가 실제 프로젝트에 맞는지 확인 (필요 없으면 삭제)
- [ ] `.env.example`에 실제로 필요한 키를 채움 (실제 `.env`는 커밋 금지, [security.md](../../rules/security.md))
- [ ] GitHub Actions CI(`.github/workflows/ci.yml`)가 push 후 통과하는지 확인
