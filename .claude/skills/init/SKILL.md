---
name: init
description: 이 템플릿을 새 프로젝트로 초기화한다 (uv 프로젝트 생성, 디렉토리 구조, 초기 설정). "프로젝트 초기화해줘", "새 저장소 세팅해줘" 같은 요청에 사용한다.
---

# init

이 저장소 자체가 재사용 템플릿이다. 새 실제 프로젝트를 시작할 때 이 스킬로 초기화한다.

## 절차

1. **의존성 초기화**
   ```bash
   uv sync
   ```
2. **디렉토리 구조 확인/생성**: `src/<package_name>/`, `tests/`가 없으면 만든다. `pyproject.toml`의
   `[project].name`을 실제 프로젝트 이름으로 바꾼다.
3. **git 초기화** (아직 git 저장소가 아니라면 사용자에게 확인 후 `git init`).
4. **CLAUDE.md / AGENTS.md 커스터마이즈**: `CLAUDE.md`의 프로젝트 개요를 실제 프로젝트에 맞게 채우고,
   `.codex/AGENTS.md`도 동일하게 갱신한다.
5. **DESIGN.md 개요 작성**: [.claude/docs/DESIGN.md](../../docs/DESIGN.md)의 "개요" 섹션을 채운다.
6. **첫 검증**: `uv run pytest`가 (테스트가 없어도) 에러 없이 돌아가는지, `uv run ruff check .`가 통과하는지
   확인한다.

## 체크리스트

- [ ] `uv sync` 성공
- [ ] `pyproject.toml`의 프로젝트명/설명 갱신
- [ ] `src/`, `tests/` 구조 존재
- [ ] CLAUDE.md, `.codex/AGENTS.md`에 실제 프로젝트 설명 반영
- [ ] `.env.example`이 필요하면 생성 (실제 `.env`는 커밋 금지, [security.md](../../rules/security.md))
