# CHANGELOG

이 프로젝트에서 진행한 작업을 날짜순으로 기록한다. 커밋 메시지의 "무엇을"보다
"왜 그렇게 결정했는지"를 남기는 데 초점을 둔다.

## 2026-07-23

- **hook 실행 로그 추가**: `.claude/hooks/`의 5개 hook이 실행될 때마다 판단 결과(제안 여부)를
  `.claude/logs/hooks.jsonl`에 한 줄씩 기록하도록 `_hooklog.py` 공유 유틸리티를 추가했다.
  기존에는 `.gitignore`에 `.claude/logs/*.jsonl` 항목만 있고 실제로 로그를 쓰는 코드가 없었다.
  로그 기록 실패가 hook 동작(제안 출력)을 막아서는 안 되므로 쓰기 예외는 조용히 무시한다.
- **sandbox/ 정리**: `sandbox/codex-test-project/`는 Codex CLI 동작 확인용 임시 프로젝트로,
  자체 `.git` 저장소를 포함하고 있어 중첩 git 문제를 일으킬 수 있었다. 저장소 루트
  `.gitignore`에 `sandbox/`를 추가해 커밋 대상에서 제외했다 (로컬 테스트 용도로만 유지).
- **uv.lock 커밋 대상 포함**: `uv sync` 실행 후 생성된 `uv.lock`을 재현 가능한 빌드를 위해
  커밋 대상에 포함했다.

## 2026-07-22

- CI(`ruff check`, `ruff format --check`, 조건부 `mypy`/`pytest`), pre-commit
  (ruff, mypy 로컬 hook), `LICENSE`(MIT), `.env.example`, VSCode 설정을 추가해 템플릿을 다듬었다.
- 전역 스킬 `harness-lab`을 프로젝트 스킬(`.claude/skills/harness-lab/`)로 복사해 비코딩 반복
  업무를 Agent/Skill/Orchestrator/Test/Evolution 구조로 하네스화할 수 있도록 지원했다.

## 2026-07-22 (초기 구성)

- Claude Code + Codex CLI 2개 도구로 협업하도록 최적화된 템플릿을 초기 구성했다
  (`.claude/rules/`, `.claude/hooks/`, `.claude/skills/`, `.codex/AGENTS.md`).
