#!/usr/bin/env python3
"""SessionStart hook.

세션 시작 시 다음을 '제안'만 한다 (차단 없음, 항상 exit 0):
- `CHANGELOG.md` 최상단(가장 최근) 항목의 헤딩 — 지난 세션에서 마지막으로 무슨 작업을
  왜 했는지 상기 (order-bridge/pc-manager/agent-visualizer-hub의 session-start-reminders.py와
  같은 패턴. 이 템플릿은 VALIDATION_PLAN.md/reports/ 같은 프로젝트 전용 진행 기록 문서가
  없어 항상 존재하는 CHANGELOG.md를 상기 대상으로 삼는다. `/init`으로 실제 프로젝트가 된 뒤에도
  그대로 유효하다).
"""

import json
import re
import sys
from pathlib import Path

from _hooklog import log_event

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

_HEADING = re.compile(r"^## (.+)$", re.MULTILINE)


def _last_changelog_heading() -> str | None:
    """`CHANGELOG.md`에서 첫 번째 `## ` 헤딩(가장 최근 항목, 새 항목이 맨 위에 추가되는
    관례)을 반환한다. 파일이 없거나 헤딩이 없으면 None.
    """
    if not CHANGELOG_PATH.exists():
        return None

    try:
        text = CHANGELOG_PATH.read_text(encoding="utf-8")
    except OSError:
        return None

    match = _HEADING.search(text)
    if not match:
        return None
    return match.group(1).strip()


def main() -> None:
    # "실패하면 그 부분만 건너뛴다"가 원칙이므로, 예상 못 한 예외(권한 오류 등)로 훅 자체가
    # 죽어 세션 시작에 영향을 주지 않도록 감싼다.
    messages = []

    try:
        last_heading = _last_changelog_heading()
    except Exception:
        last_heading = None
    if last_heading:
        messages.append(f"CHANGELOG.md 최근 항목: {last_heading}")

    if not messages:
        log_event("session-start-reminders", "SessionStart", triggered=False)
        sys.exit(0)

    log_event("session-start-reminders", "SessionStart", triggered=True, detail="; ".join(messages))
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "[session-start-reminders]\n"
                    + "\n".join(f"- {m}" for m in messages),
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # 이 훅은 세션 시작을 절대 막으면 안 된다 — 어떤 이유로든 실패하면 조용히 넘어간다.
        sys.exit(0)
