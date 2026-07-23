#!/usr/bin/env python3
"""PostToolUse hook (matcher: Bash).

pytest 실행 결과가 실패로 보이면 Codex 원인 분석을 '제안'한다. 절대 차단하지 않는다.
"""

import json
import re
import sys

from _hooklog import log_event

# 줄 시작 기준으로 매칭해 테스트 이름/로그 문구에 "failed"가 우연히 포함된 경우의 오탐을 줄인다
# (예: test_login_failed_when_wrong_password).
FAILURE_PATTERNS = (
    re.compile(r"^FAILED\s", re.MULTILINE),
    re.compile(r"^ERROR\s", re.MULTILINE),
    re.compile(r"^E\s", re.MULTILINE),
    re.compile(r"\b\d+ failed\b"),
    re.compile(r"Traceback \(most recent call last\)"),
)


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

    if not any(pattern.search(output) for pattern in FAILURE_PATTERNS):
        log_event("post-test-analysis", "PostToolUse", triggered=False)
        sys.exit(0)

    log_event("post-test-analysis", "PostToolUse", triggered=True)
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
