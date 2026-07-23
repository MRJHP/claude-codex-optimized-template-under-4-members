# CHANGELOG

이 프로젝트에서 진행한 작업을 날짜순으로 기록한다. 커밋 메시지의 "무엇을"보다
"왜 그렇게 결정했는지"를 남기는 데 초점을 둔다.

## 2026-07-23 (2차 검토)

- **CI 조건부 스킵 제거**: `src/`, `tests/`에 항상 최소 예제가 존재하게 되어(1차 검토에서 추가) `mypy`/`pytest`를
  `hashFiles`로 건너뛰던 조건이 항상 참이 되었다. 조건을 제거해 무조건 실행하도록 바꿨다 — 초기화 중 실수로
  예제를 통째로 지워도 CI가 조용히 "건너뛰기"로 통과하는 fail-open을 막기 위함. `CLAUDE.md`의 관련 설명도
  갱신했다.
- **`/init` 체크리스트에 예제 교체 안내 추가**: `src/project/__init__.py`, `tests/test_project.py` 예제를
  실제 프로젝트로 초기화할 때 교체/삭제하라는 항목이 빠져 있어 추가했다.
- **훅 중복 제거**: `check-codex-before-write.py`와 `post-implementation-review.py`에 토씨 하나 같은
  `RISK_PATH_KEYWORDS` 튜플이 중복돼 있어 `.claude/hooks/_risk_keywords.py` 공유 모듈로 뽑아냈다.
- **`post-test-analysis.py` 오탐 완화**: `"failed"`, `"ERROR"` 부분 문자열 매칭이 `test_login_failed_...`
  같은 테스트 이름에도 우연히 매칭될 수 있어, 줄 시작 기준 정규식(`^FAILED `, `^ERROR `, `^E `, `\d+ failed`)으로
  바꿨다.
- **`.vscode/settings.json` 중복 설정 제거**: `mypy-type-checker.args: ["--strict"]`가 `pyproject.toml`의
  `[tool.mypy] strict = true`와 중복이라 제거했다. mypy 확장은 워크스페이스의 `pyproject.toml` 설정을 그대로
  사용한다.

Codex와 구조를 재검토해 위 항목들을 발견했다.

## 2026-07-23

- **Codex 컨텍스트 로드 경로 버그 수정**: `.codex/AGENTS.md`와 `.codex/skills/context-loader/SKILL.md`가
  존재하지 않는 `.claude/CLAUDE.md`를 가리키고 있었다 (실제 파일은 저장소 루트의 `CLAUDE.md`). Codex가 세션
  시작 시 컨텍스트 로드 1단계부터 실패하는 문제라 두 파일의 경로를 수정했다. Codex와 협업해 구조를 점검하는
  과정에서 발견했다.
- **템플릿 상태에서도 pytest가 바로 동작하도록 최소 예제 추가**: `pyproject.toml`의 `--cov=src`,
  `testpaths=["tests"]`가 실제 `src/`, `tests/` 없이 하드코딩되어 있어 README 안내대로 `uv run pytest`를
  실행하면 실패했다. `src/project/__init__.py` (예제 함수)와 `tests/test_project.py` (smoke test)를 추가하고,
  `src`가 설치되지 않는 `package = false` 구성에서도 임포트되도록 `pythonpath = ["src"]`를 pytest 설정에
  추가했다. `/init` 스킬로 실제 프로젝트를 만들 때 이 예제를 실제 코드로 교체하면 된다.
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
