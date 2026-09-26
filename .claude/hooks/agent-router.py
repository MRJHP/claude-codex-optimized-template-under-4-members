#!/usr/bin/env python3
"""UserPromptSubmit hook.

사용자 입력을 보고 (1) 어떤 스킬이 적합한지, (2) 서브에이전트로 위임한다면 어떤 작업 유형이라
어느 에이전트(=모델)가 맞는지를 '제안'만 한다. 절대 차단하지 않는다(항상 exit 0). Claude가
additionalContext를 참고해서 실제로 그 스킬·에이전트를 쓸지 스스로 판단한다.

모델 힌트의 기준은 CLAUDE.md "Agent 모델 선택"(정본은 harness-lab `references/agent-design.md`의
루브릭)이다: 조사·검색은 `explorer`(Haiku), 확립된 패턴 구현·버그 수정은 `implementer`(Sonnet),
설계·상충 해소·복잡한 분석은 `architect`(Opus), 장시간 자율·전수 점검·다단계 검증은
`verifier`(Fable). 메인 세션의 모델(`/model`)은 훅으로 바꿀 수 없으므로 이 힌트는 서브에이전트
위임에만 해당한다 — 위임할 만한 크기가 아니면 무시하면 된다.

우선순위: 한 입력이 여러 유형에 걸치면 깊은 추론이 필요한 쪽(verifier > architect)을 먼저
고른다. 조사와 구현이 섞인 "찾아서 고쳐줘"는 구현으로 본다(implementer > explorer).
"""

import json
import sys

from _hooklog import log_event, read_hook_input

SKILL_HINTS = [
    (("새 프로젝트", "프로젝트 시작", "새로 시작"), "startproject"),
    (("계획", "구현 계획", "plan"), "plan"),
    (("테스트", "tdd", "버그 수정"), "tdd"),
    (("리팩토링", "단순화", "정리해"), "simplify"),
    (("라이브러리", "패키지 조사", "뭐가 나을까"), "research-lib"),
    (("설계", "design.md", "아키텍처 문서"), "update-design / design-tracker"),
    (("codex", "코덱스", "세컨드 오피니언"), "codex-system"),
    (("초기화", "init", "새 저장소"), "init"),
    (("여기까지 정리", "이어서 하게 기록", "체크포인트"), "checkpointing"),
    (("하네스", "에이전트와 스킬 설계", "리포트로 만들어"), "harness-lab"),
    (("라이브러리 문서", "의존성 추가"), "update-lib-docs"),
]

# (키워드, 작업 유형 라벨, 에이전트 이름, 모델) — 위에서부터 우선.
AGENT_HINTS = [
    (
        (
            "전수",
            "빠짐없이",
            "전부 점검",
            "전체 점검",
            "감사해",
            "실제로 돌려",
            "끝까지 검증",
            "장시간",
        ),
        "장시간 자율·다단계 검증",
        "verifier",
        "Fable",
    ),
    (
        (
            "설계",
            "아키텍처",
            "구조를",
            "어느 쪽이",
            "어느 게",
            "트레이드오프",
            "리팩토링",
            "원인 분석",
            "왜 안",
        ),
        "설계·상충 해소·복잡한 분석",
        "architect",
        "Opus",
    ),
    (
        ("구현해", "만들어", "추가해", "수정해", "고쳐", "버그", "적용해", "바꿔줘", "통과시켜"),
        "확립된 패턴 구현·버그 수정",
        "implementer",
        "Sonnet",
    ),
    (
        ("찾아", "어디에", "어디 있", "현황", "목록", "검색", "확인해", "정리해서 보여", "표로"),
        "조사·검색·현황 파악",
        "explorer",
        "Haiku",
    ),
]


def match_skills(prompt: str) -> list[str]:
    matched = [skill for keywords, skill in SKILL_HINTS if any(k in prompt for k in keywords)]
    return list(dict.fromkeys(matched))


def match_agent(prompt: str) -> tuple[str, str, str] | None:
    """(작업 유형 라벨, 에이전트, 모델) — 우선순위가 가장 높은 한 가지만 돌려준다."""
    for keywords, label, agent, model in AGENT_HINTS:
        if any(k in prompt for k in keywords):
            return label, agent, model
    return None


def build_suggestion(skills: list[str], agent: tuple[str, str, str] | None) -> str:
    parts: list[str] = []
    if skills:
        parts.append("관련될 수 있는 스킬: " + ", ".join(skills) + ".")
    if agent:
        label, name, model = agent
        parts.append(
            f"작업 유형 추정: {label} → 서브에이전트로 위임한다면 `{name}`({model}) 권장 "
            "(CLAUDE.md 'Agent 모델 선택' 기준. 메인 세션 모델은 바뀌지 않으며, 위임할 크기가 "
            "아니면 무시)."
        )
    return (
        "[agent-router] "
        + " ".join(parts)
        + " 상황에 맞으면 참고하되, 적합하지 않으면 무시해도 됩니다."
    )


def main() -> None:
    data = read_hook_input()

    prompt = str(data.get("prompt", "")).lower()
    skills = match_skills(prompt)
    agent = match_agent(prompt)

    if not skills and agent is None:
        log_event("agent-router", "UserPromptSubmit", triggered=False)
        sys.exit(0)

    detail_parts = list(skills)
    if agent:
        detail_parts.append(f"{agent[1]}({agent[2]})")
    log_event("agent-router", "UserPromptSubmit", triggered=True, detail=", ".join(detail_parts))
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": build_suggestion(skills, agent),
                }
            },
            ensure_ascii=False,
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
