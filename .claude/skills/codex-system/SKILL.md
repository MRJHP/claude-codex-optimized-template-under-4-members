---
name: codex-system
description: Codex CLI 연계 구조를 자세히 설명한다. Codex를 언제/어떻게 호출하는지, hook과 rules가 어떻게 맞물리는지 알고 싶을 때 사용한다.
---

# codex-system

이 템플릿에서 Claude Code와 Codex CLI가 어떻게 연결되어 있는지에 대한 참고 문서.

## 연결 방식

- Codex는 Bash로 `codex exec --json --sandbox read-only`(신규 세션)/`codex exec --sandbox read-only resume <thread_id> --json`
  (같은 세션 이어가기 — `--sandbox`는 `resume` 앞)을 호출해 부른다(2026-09-12부터 — 이전에는 `mcp__codex__codex`/`mcp__codex__codex-reply`
  MCP 도구였으나 Codex CLI 0.154.0에서 `codex mcp-server`가 삭제되며 전환).
- `.claude/agents/general-purpose.md` 서브에이전트는 Bash 도구 권한을 가지고 있어, 조사 작업 중에도
  필요하면 Codex를 호출할 수 있다.
- `.claude/agents/pm.md` 서브에이전트는 작업 분해·진행 상황 추적을 전담한다. 코드를 직접 쓰지 않고,
  CHANGELOG.md/git log/DESIGN.md를 근거로 언제 Codex 상담이 필요한지 판단 근거를 정리해서 메인
  오케스트레이터에게 반환한다.
- 저장소 루트 `AGENTS.md`는 Codex 쪽에서 보는 프로젝트 컨텍스트 문서다. `CLAUDE.md`와 짝을 이룬다
  (Codex CLI는 git 루트→cwd 경로의 `AGENTS.md`만 자동으로 읽으므로, `.codex/` 같은 하위 폴더에 두면
  자동 로드되지 않는다 — 2026-09-14 이 경로로 정정).
- `.codex/skills/context-loader/`는 Codex가 `.claude/rules/`, `.claude/docs/DESIGN.md`를 함께 참고하도록
  안내해서, Claude와 Codex가 같은 규칙 아래에서 작업하게 한다.

## Hook은 강제가 아니라 제안

`.claude/hooks/`의 hook은 전부 **차단하지 않는다** (`additionalContext`로 제안만 하거나 로그만 남긴다).
`session-start-reminders.py`, `agent-router.py`, `check-codex-before-write.py`,
`check-codex-after-plan.py`, `post-implementation-review.py`, `post-test-analysis.py`는 Codex 위임을
제안하거나 세션 시작 시 컨텍스트를 상기시키는 훅이고, `log-codex-call.py`는 실제 Codex 호출이
일어났을 때 그 사실을 로그로 남기는 훅이다(전체 표는 [CLAUDE.md](../../../CLAUDE.md#자동-협업-hook)가 정본). 즉:

- Hook이 "Codex 상담을 제안합니다"라고 메시지를 띄워도, 그 작업이 계속 진행된다.
- Codex를 실제로 호출할지 말지는 Claude가 [codex-delegation.md](../../rules/codex-delegation.md) 기준으로
  스스로 판단한다.
- 제안 훅은 `permissionDecision`을 출력하지 않는다. PreToolUse에서 `"allow"`를 내면 사용자 승인 없이
  도구가 실행되는 권한 우회가 되고 사유 문구도 Claude에게 전달되지 않기 때문이다(근거는
  [CLAUDE.md](../../../CLAUDE.md#자동-협업-hook)의 실험 결과).
- Hook 로직을 더 엄격하게(차단형으로) 바꾸고 싶다면 그 hook에 `permissionDecision`을 `"ask"`나
  `"deny"`로 **새로** 추가하고, 의도한 차단인지 `tests/test_hooks.py`의 계약 테스트
  (`test_no_hook_source_emits_a_permission_decision`)도 함께 갱신한다.

## 언제 Codex를 부르나 (요약)

구현 전 상담 / 구현 후 리뷰 / 반복 실패 시 세컨드 오피니언 / 사용자 명시적 요청. 자세한 기준은
[codex-delegation.md](../../rules/codex-delegation.md).

## 좋은 위임 예시

```bash
codex exec --json --sandbox read-only - <<'CODEX_PROMPT'
다음 함수가 동시성 환경에서 안전한지 검토해줘. 파일: src/cache.py:42-70 (아래 첨부).
이미 lock을 추가하는 방법을 고려했지만 성능 저하가 우려돼서 보류했어.
락 없이 안전하게 만들 방법이 있는지, 혹은 락이 불가피한지 판단해줘.
CODEX_PROMPT
```

(프롬프트를 `"..."`로 셸 인용하지 않는 이유는 [codex-delegation.md](../../rules/codex-delegation.md) 참고.)
