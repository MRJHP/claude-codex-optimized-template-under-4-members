#!/usr/bin/env python3
"""PostToolUse hook (matcher: Bash).

pytest 실행 결과가 실패로 보이면 Codex 원인 분석을 '제안'한다. 절대 차단하지 않는다.
"""

import json
import sys

FAILURE_MARKERS = ("FAILED", "ERROR", "failed", "Traceback (most recent call last)")


def main() -> None:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        data = {}

    tool_input = data.get("tool_input", {}) or {}
    command = str(tool_input.get("command", ""))
    if "pytest" not in command:
        sys.exit(0)

    tool_response = data.get("tool_response", {}) or {}
    output = str(tool_response.get("stdout", "")) + str(tool_response.get("stderr", ""))

    if not any(marker in output for marker in FAILURE_MARKERS):
        sys.exit(0)

    suggestion = (
        "[post-test-analysis] pytest 실행이 실패한 것으로 보입니다. "
        "같은 실패를 2회 이상 반복해서 해결하지 못했다면 mcp__codex__codex로 "
        "Codex에게 실패 로그와 관련 코드를 공유하고 원인 분석을 요청할 것을 제안합니다 (강제 아님)."
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": suggestion,
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
