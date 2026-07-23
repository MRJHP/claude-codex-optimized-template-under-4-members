#!/usr/bin/env python3
"""UserPromptSubmit hook.

사용자 입력을 보고 어떤 스킬/작업 흐름이 적합한지 '제안'만 한다. 절대 차단하지 않는다
(항상 exit 0). Claude가 additionalContext를 참고해서 실제로 그 스킬을 쓸지 스스로 판단한다.
"""

import json
import sys

from _hooklog import log_event

SKILL_HINTS = [
    (("새 프로젝트", "프로젝트 시작", "새로 시작"), "startproject"),
    (("계획", "구현 계획", "plan"), "plan"),
    (("테스트", "tdd", "버그 수정"), "tdd"),
    (("리팩토링", "단순화", "정리해"), "simplify"),
    (("라이브러리", "패키지 조사", "뭐가 나을까"), "research-lib"),
    (("설계", "design.md", "아키텍처 문서"), "update-design / design-tracker"),
    (("codex", "코덱스", "세컨드 오피니언"), "codex-system"),
    (("초기화", "init", "새 저장소"), "init"),
]


def main() -> None:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        data = {}

    prompt = str(data.get("prompt", "")).lower()
    matched = [skill for keywords, skill in SKILL_HINTS if any(k in prompt for k in keywords)]

    if not matched:
        log_event("agent-router", "UserPromptSubmit", triggered=False)
        sys.exit(0)

    matched_skills = ", ".join(dict.fromkeys(matched))
    suggestion = (
        "[agent-router] 이 요청과 관련될 수 있는 스킬: "
        + matched_skills
        + ". 상황에 맞으면 참고하되, 적합하지 않으면 무시해도 됩니다."
    )
    log_event("agent-router", "UserPromptSubmit", triggered=True, detail=matched_skills)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": suggestion,
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
