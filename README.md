# Claude + Codex CLI 최적화 템플릿

Claude Code와 Codex CLI 2개 도구만으로 협업하도록 구성된 프로젝트 템플릿입니다.
Claude Code가 오케스트레이터(요구사항 파악 · 계획 · 구현 · 웹 리서치)를 맡고,
Codex CLI는 MCP 도구 `mcp__codex__codex`로 호출되어 리뷰를 전담합니다.

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

**Codex 연동**: `.mcp.json`에 Codex가 프로젝트 MCP 서버로 등록되어 있다
(`npx -y @openai/codex@0.153.4 mcp-server`). `codex mcp-server`는 Codex CLI 0.154.0에서 삭제됐기
때문에 마지막 지원 버전을 npx로 고정한 것이다. 전역 Codex CLI 설치는 필요 없고, 저장소를 clone한
사람은 Node.js(npx)와 Codex 로그인만 있으면 된다(로그인 상태는 `~/.codex/auth.json`에 저장되어
저장소와 무관함):

```bash
npx -y @openai/codex@0.153.4 login   # 최초 1회, 각자 자기 계정으로 로그인
```

Codex 호출 경로는 MCP `codex` 도구 하나뿐이다. Bash `codex exec` 같은 다른 호출 방식은 쓰지 않는다.

- Claude Code가 이 저장소의 MCP 서버를 처음 인식하면 신뢰 여부를 묻는다. 승인 후 `claude mcp list`에
  `codex: ✓ Connected`가 보이면 준비 완료다.
- `.mcp.json`의 `command`는 Windows용 `cmd /c npx ...` 형태다. macOS/Linux에서는 `command`를
  `npx`, `args`를 `["-y", "@openai/codex@0.153.4", "mcp-server"]`로 바꾼다.
- 호출은 항상 `sandbox: read-only`·`approval-policy: never`이며 `.claude/hooks/codex-disable-plugins.py`가
  이를 강제한다. 세부 호출 규칙은 [codex-delegation.md](.claude/rules/codex-delegation.md) 참고.
- 알려진 한계: npm에서 `0.153.4`가 내려가면(unpublish) 서버가 뜨지 않는다.
