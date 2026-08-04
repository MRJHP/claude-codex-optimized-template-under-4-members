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

**Codex 연동**: `.mcp.json`에 `codex mcp-server`가 프로젝트 MCP 서버로 등록되어 있어, 저장소를
클론한 사람은 별도 설정 없이 바로 Claude Code에서 `mcp__codex__codex` 도구를 쓸 수 있다. 단,
인증은 각자 로컬 Codex CLI 계정으로 개별 진행해야 한다 (`.mcp.json`에는 인증 정보가 전혀 없고,
로그인 상태는 각자의 `~/.codex/auth.json`에 저장되어 저장소와 무관함):

```bash
codex login                   # 최초 1회, 각자 자기 계정으로 로그인
```

Claude Code가 새 프로젝트 MCP 서버를 처음 인식하면 신뢰 여부를 묻는 승인 프롬프트가 뜬다
(세션 재시작 필요할 수 있음).
