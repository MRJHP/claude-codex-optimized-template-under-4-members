---
name: codex-system
description: Codex CLI 연계 구조를 자세히 설명한다. Codex를 언제/어떻게 호출하는지, hook과 rules가 어떻게 맞물리는지 알고 싶을 때 사용한다.
---

# codex-system

이 템플릿에서 Claude Code와 Codex CLI가 어떻게 연결되어 있는지에 대한 참고 문서.

## 연결 방식

- Codex는 **MCP 도구**로 연결되어 있다: `mcp__codex__codex`(신규 세션 시작), `mcp__codex__codex-reply`(같은
  Codex 세션 이어가기). 별도 CLI 셸아웃이 아니라 Claude가 도구 호출로 직접 부른다.
- `.claude/agents/general-purpose.md` 서브에이전트는 이 두 도구에 접근 권한을 가지고 있어, 조사 작업 중에도
  필요하면 Codex를 호출할 수 있다.
- `.codex/AGENTS.md`는 Codex 쪽에서 보는 프로젝트 컨텍스트 문서다. 저장소 루트 `CLAUDE.md`와 짝을 이룬다.
- `.codex/skills/context-loader/`는 Codex가 `.claude/rules/`, `.claude/docs/DESIGN.md`를 함께 참고하도록
  안내해서, Claude와 Codex가 같은 규칙 아래에서 작업하게 한다.

## Hook은 강제가 아니라 제안

`.claude/hooks/`의 6개 hook은 전부 **차단하지 않는다** (`permissionDecision: allow` 또는 `additionalContext`만
반환). 이 중 5개는 Codex 위임을 제안하는 훅이고, `log-codex-call.py` 1개는 실제 Codex 호출이 일어났을 때
그 사실을 로그로 남기는 훅이다. 즉:

- Hook이 "Codex 상담을 제안합니다"라고 메시지를 띄워도, 그 작업이 계속 진행된다.
- Codex를 실제로 호출할지 말지는 Claude가 [codex-delegation.md](../../rules/codex-delegation.md) 기준으로
  스스로 판단한다.
- Hook 로직을 더 엄격하게(차단형으로) 바꾸고 싶다면 각 hook의 `permissionDecision`을 `"ask"`나 `"deny"`로
  바꾸면 된다.

## 언제 Codex를 부르나 (요약)

구현 전 상담 / 구현 후 리뷰 / 반복 실패 시 세컨드 오피니언 / 사용자 명시적 요청. 자세한 기준은
[codex-delegation.md](../../rules/codex-delegation.md).

## 좋은 위임 예시

```
mcp__codex__codex 호출:
"다음 함수가 동시성 환경에서 안전한지 검토해줘. 파일: src/cache.py:42-70 (아래 첨부).
이미 lock을 추가하는 방법을 고려했지만 성능 저하가 우려돼서 보류했어.
락 없이 안전하게 만들 방법이 있는지, 혹은 락이 불가피한지 판단해줘."
```
