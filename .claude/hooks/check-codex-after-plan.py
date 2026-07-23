#!/usr/bin/env python3
"""PreToolUse hook (matcher: ExitPlanMode).

계획이 확정되어 실행 단계로 넘어가기 직전, 계획 내용이 복잡해 보이면 Codex 리뷰를 '제안'한다.
절대 차단하지 않는다 (permissionDecision은 항상 allow).
"""

import json
import sys

from _hooklog import log_event

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
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        data = {}

    tool_input = data.get("tool_input", {}) or {}
    plan_text = str(tool_input.get("plan", ""))

    triggered = len(plan_text) > 1500 or any(k in plan_text.lower() for k in RISK_KEYWORDS)
    if not triggered:
        log_event("check-codex-after-plan", "PreToolUse", triggered=False)
        sys.exit(0)

    log_event(
        "check-codex-after-plan", "PreToolUse", triggered=True, detail=f"plan_len={len(plan_text)}"
    )
    reason = (
        "[check-codex-after-plan] 계획이 크거나 되돌리기 어려운 변경을 포함하는 것으로 보입니다. "
        "실행에 들어가기 전에 mcp__codex__codex로 Codex에게 계획 리뷰를 받아볼 것을 제안합니다 "
        "(강제 아님)."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
