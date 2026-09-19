#!/usr/bin/env python3
"""PreToolUse hook (matcher: ExitPlanMode).

계획이 확정되어 실행 단계로 넘어가기 직전, 계획 내용이 복잡해 보이면 Codex 리뷰를 '제안'한다.
절대 차단하지 않는다.

제안은 `hookSpecificOutput.additionalContext`로만 전달한다. `permissionDecision`은 출력하지
않는다 — PreToolUse에서 `allow`를 내면 사용자 승인 없이 도구가 실행되는 권한 우회가 되고,
`permissionDecisionReason`은 Claude에게 전달되지도 않는다(2026-09-19 실험, Claude Code 2.1.278.
자세한 근거는 CLAUDE.md '자동 협업 Hook' 절). 제안이 없으면 아무것도 출력하지 않고 종료한다.
"""

import json
import sys

from _hooklog import already_suggested, as_dict, log_event, read_hook_input

RISK_KEYWORDS = (
    "migration",
    "schema",
    "인증",
    "auth",
    "payment",
    "결제",
    "삭제",
    "delete",
    "breaking",
)


def main() -> None:
    data = read_hook_input()

    tool_input = as_dict(data.get("tool_input"))
    plan_text = str(tool_input.get("plan", ""))
    session_id = str(data.get("session_id", ""))

    triggered = len(plan_text) > 1500 or any(k in plan_text.lower() for k in RISK_KEYWORDS)
    if not triggered:
        log_event("check-codex-after-plan", "PreToolUse", triggered=False)
        sys.exit(0)

    if already_suggested(session_id, "check-codex-after-plan"):
        # 이번 호출은 아무 메시지도 출력하지 않으므로(알림 피로 억제) status를 기본값 "flag"
        # (제안됨)가 아니라 "working"으로 남겨, 시각화가 실제로 일어나지 않은 제안을 반복 표시하지
        # 않게 한다.
        log_event(
            "check-codex-after-plan",
            "PreToolUse",
            triggered=True,
            detail=f"plan_len={len(plan_text)} (deduped)",
            status="working",
        )
        sys.exit(0)

    log_event(
        "check-codex-after-plan", "PreToolUse", triggered=True, detail=f"plan_len={len(plan_text)}"
    )
    suggestion = (
        "[check-codex-after-plan] 계획이 크거나 되돌리기 어려운 변경을 포함하는 것으로 보입니다. "
        "실행에 들어가기 전에 Bash로 codex exec를 호출해 Codex에게 계획 리뷰를 받아볼 것을 "
        "제안합니다 (강제 아님)."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": suggestion,
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
