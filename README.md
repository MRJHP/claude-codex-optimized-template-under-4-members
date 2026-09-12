# Claude + Codex CLI 최적화 템플릿

Claude Code와 Codex CLI 2개 도구만으로 협업하도록 구성된 프로젝트 템플릿입니다.
Claude Code가 오케스트레이터(요구사항 파악 · 계획 · 구현 · 웹 리서치)를 맡고,
Codex CLI는 Bash로 `codex exec`를 호출해 리뷰를 전담합니다.

자세한 협업 구조, 규칙, 스킬, 품질 게이트는 [CLAUDE.md](CLAUDE.md)를 참고하세요.
작업 이력은 [CHANGELOG.md](CHANGELOG.md)에 날짜순으로 기록됩니다.
전체 구조를 한눈에 보려면 [archive/Claude_Codex_최적화_템플릿_설명서.png](archive/Claude_Codex_최적화_템플릿_설명서.png)
설명 이미지를 참고하세요.

## 시작하기

```bash
uv sync                       # 의존성 설치
uv run pre-commit install     # 커밋 전 ruff/mypy 자동 실행 활성화
```

새 프로젝트로 초기화하려면 Claude Code에서 `/init` 스킬을 사용하세요.

**Codex 연동**: Codex는 MCP 서버로 등록하지 않는다(Codex CLI 0.154.0에서 `codex mcp-server`가
삭제됨, 2026-09-12). 저장소를 clone한 사람은 로컬에 Codex CLI(`npm install -g @openai/codex`)를
설치하고, 각자 자기 계정으로 로그인만 하면 된다(로그인 상태는 `~/.codex/auth.json`에 저장되어
저장소와 무관함):

```bash
codex login                   # 최초 1회, 각자 자기 계정으로 로그인
```

Claude Code는 Bash로 `codex exec`를 직접 호출해 Codex와 협업한다 — 별도의 MCP 승인 프롬프트나
`claude mcp list` 확인은 필요 없다. 세부 호출 규칙은 [codex-delegation.md](.claude/rules/codex-delegation.md) 참고.
