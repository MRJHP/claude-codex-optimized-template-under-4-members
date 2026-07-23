#!/usr/bin/env python3
"""PostToolUse hook (matcher: Edit|Write).

파일을 편집/작성한 직후, 위험도가 높아 보이면 Codex 리뷰를 '제안'한다. 절대 차단하지 않는다.
"""

import json
import sys

from _hooklog import log_event
from _risk_keywords import RISK_PATH_KEYWORDS


def main() -> None:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        data = {}

    tool_input = data.get("tool_input", {}) or {}
    file_path = str(tool_input.get("file_path", "")).lower()

    if not file_path or not any(k in file_path for k in RISK_PATH_KEYWORDS):
        log_event("post-implementation-review", "PostToolUse", triggered=False, detail=file_path)
        sys.exit(0)

    log_event("post-implementation-review", "PostToolUse", triggered=True, detail=file_path)
    suggestion = (
        f"[post-implementation-review] '{file_path}' 변경이 완료되었습니다. "
        "민감한 영역이므로 mcp__codex__codex로 Codex에게 리뷰를 받아볼 것을 제안합니다 (강제 아님)."
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
