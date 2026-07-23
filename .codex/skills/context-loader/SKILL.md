---
name: context-loader
description: Codex가 .claude/ 아래의 규칙과 설계 문서를 로드해서 Claude와 동일한 컨텍스트로 작업하게 한다. Codex 세션 시작 시 항상 적용한다.
---

# context-loader

Claude Code와 Codex CLI가 서로 다른 규칙을 적용하면 리뷰/구현이 어긋난다. 이 스킬은 Codex가 `.claude/`
아래의 공유 컨텍스트를 빠짐없이 읽도록 안내한다.

## 로드 순서

1. `CLAUDE.md` (저장소 루트) — 전체 협업 구조와 규칙 목록 인덱스
2. `.claude/rules/language.md` — 응답 언어(한국어) 및 용어 규칙
3. `.claude/rules/codex-delegation.md` — Codex 자신이 언제/어떻게 호출되는지에 대한 기준
4. `.claude/rules/coding-principles.md` — 리뷰 시 적용할 코드 품질 기준
5. `.claude/rules/dev-environment.md` — uv/ruff/mypy/pytest 명령
6. `.claude/rules/security.md` — 보안 리뷰 기준
7. `.claude/rules/testing.md` — 테스트 리뷰 기준 (TDD, AAA, 커버리지 80%)
8. `.claude/docs/DESIGN.md` — 현재까지의 아키텍처 결정. 리뷰 의견이 기존 결정과 상충하면 그 사실을
   명시적으로 짚어준다.

## 사용 시점

- Codex가 `mcp__codex__codex`로 새로 호출될 때마다, 위임 프롬프트에 포함된 맥락만으로 부족하면 위 파일들을
  직접 읽어 보충한다.
- `mcp__codex__codex-reply`로 같은 세션을 이어갈 때는 이미 로드한 컨텍스트를 다시 읽을 필요는 없다.

## 주의

- `.claude/docs/research/`, `.claude/docs/libraries/`는 필요할 때만 선택적으로 읽는다 (매번 전체를 읽지
  않는다) — 위임 프롬프트가 특정 주제를 언급하면 관련 파일만 확인한다.
