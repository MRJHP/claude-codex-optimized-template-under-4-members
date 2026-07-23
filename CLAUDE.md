# 프로젝트 메인 문서

이 저장소는 **Claude Code + Codex CLI** 2개 도구만으로 협업하도록 최적화된 템플릿입니다.
(Gemini CLI는 제거되었으며, 웹 리서치는 Claude의 WebSearch가 직접 담당합니다.)

## 협업 구조

- **Claude Code**: 오케스트레이터 + 리서치. 요구사항 파악, 계획 수립, 코드 작성, WebSearch를 통한 리서치를 담당합니다.
- **Codex CLI**: 리뷰 전담. `mcp__codex__codex` 도구를 통해 Claude가 직접 호출하며, 구현 전 상담·구현 후 리뷰·막혔을 때 세컨드 오피니언 역할을 합니다.
- 역할 분담의 세부 기준은 [.claude/rules/codex-delegation.md](.claude/rules/codex-delegation.md)를 따릅니다.

## 항상 지켜야 할 규칙

`.claude/rules/`에 정의된 6개 규칙은 모든 세션에서 항상 적용됩니다:

| 파일 | 내용 |
|---|---|
| [language.md](.claude/rules/language.md) | 언어 설정 (영어로 사고, 한국어로 응답) |
| [codex-delegation.md](.claude/rules/codex-delegation.md) | Codex 위임 규칙 |
| [coding-principles.md](.claude/rules/coding-principles.md) | 단순성, 단일 책임, 조기 반환 |
| [dev-environment.md](.claude/rules/dev-environment.md) | uv, ruff, mypy, pytest 사용법 |
| [security.md](.claude/rules/security.md) | 기밀 정보 관리, 입력 검증 |
| [testing.md](.claude/rules/testing.md) | TDD, AAA 패턴, 커버리지 80% |

## 지식 베이스

- [.claude/docs/DESIGN.md](.claude/docs/DESIGN.md) — 설계 문서 (변경 시 자동 업데이트 대상)
- `.claude/docs/research/` — Claude WebSearch로 조사한 주제별 리서치 결과
- `.claude/docs/libraries/` — 사용 중인 라이브러리 문서 요약
- [CHANGELOG.md](CHANGELOG.md) — 작업 이력 로그 (날짜별로 무엇을 왜 바꿨는지 기록)
- `.claude/logs/hooks.jsonl` — hook 실행 로그 (커밋 대상 아님, 로컬 디버깅용)

## 자동 협업 Hook

`.claude/hooks/`의 5개 Python hook은 **차단 없이 제안만 출력**합니다. 실제로 Codex를 호출할지는
Claude가 상황을 보고 스스로 판단합니다.

| Hook | 시점 | 역할 |
|---|---|---|
| agent-router.py | 사용자 입력 시 | 입력 내용에서 어떤 스킬/작업 흐름이 적합한지 제안 |
| check-codex-before-write.py | 파일 편집 전 | 위험도가 높은 변경이면 Codex 상담 제안 |
| check-codex-after-plan.py | 계획 확정 후 | Codex에게 계획 리뷰를 받을지 제안 |
| post-implementation-review.py | 구현 후 | Codex 코드 리뷰 제안 |
| post-test-analysis.py | 테스트 실행 후 | 테스트 실패 시 Codex 원인 분석 제안 |

## 스킬

`.claude/skills/`에 13개(스킬 12개 + Codex 연계 문서 스킬 1개) 스킬이 정의되어 있습니다.
자세한 목록은 [.claude/skills/codex-system/SKILL.md](.claude/skills/codex-system/SKILL.md)를 참고하세요.
[harness-lab](.claude/skills/harness-lab/SKILL.md)은 코딩 외 반복 업무(리포트·체크리스트·문서 산출물)를
Agent/Skill/Orchestrator/Test/Evolution 구조로 만드는 별도 스킬로, 기존 코딩 규칙과 별개로 동작합니다.

## Codex 설정

`.codex/AGENTS.md`는 Codex CLI용 컨텍스트 문서이며, `.codex/skills/context-loader/`는
Codex가 `.claude/` 아래의 규칙·설계 문서를 동일하게 로드하도록 안내합니다.

## 품질 게이트

- **CI**: `.github/workflows/ci.yml`이 push/PR마다 `ruff check`, `ruff format --check`, `mypy`, `pytest`를
  실행합니다. `src/`, `tests/`에는 최소 예제(`src/project`, `tests/test_project.py`)가 포함되어 있어 항상
  통과하며, `/init` 스킬로 실제 프로젝트로 바꿀 때 이 예제를 실제 코드로 교체합니다.
- **pre-commit**: `.pre-commit-config.yaml`에 ruff check/format, mypy가 로컬 hook으로 등록되어 있습니다.
  `uv run pre-commit install`로 최초 1회 활성화합니다 ([dev-environment.md](.claude/rules/dev-environment.md)).
- **에디터**: `.vscode/settings.json`, `.vscode/extensions.json`으로 ruff/mypy 확장 및 저장 시 자동 포맷을
  구성해 두었습니다.
- **라이선스/환경변수**: `LICENSE`(MIT, 필요 없으면 삭제), `.env.example`(`.env`로 복사해서 사용, 실제 값은
  절대 커밋하지 않음 — [security.md](.claude/rules/security.md)).
