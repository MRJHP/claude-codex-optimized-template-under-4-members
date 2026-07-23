# Claude + Codex CLI 최적화 템플릿

Claude Code와 Codex CLI 2개 도구만으로 협업하도록 구성된 프로젝트 템플릿입니다.
Claude Code가 오케스트레이터(요구사항 파악 · 계획 · 구현 · 웹 리서치)를 맡고,
Codex CLI는 `mcp__codex__codex` 도구로 호출되어 리뷰를 전담합니다.

자세한 협업 구조, 규칙, 스킬, 품질 게이트는 [CLAUDE.md](CLAUDE.md)를 참고하세요.
작업 이력은 [CHANGELOG.md](CHANGELOG.md)에 날짜순으로 기록됩니다.

## 시작하기

```bash
uv sync                       # 의존성 설치
uv run pre-commit install     # 커밋 전 ruff/mypy 자동 실행 활성화
```

새 프로젝트로 초기화하려면 Claude Code에서 `/init` 스킬을 사용하세요.
