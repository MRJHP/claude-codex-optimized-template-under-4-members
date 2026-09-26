#!/usr/bin/env python3
"""PreToolUse hook (matcher: mcp__codex__codex).

`mcp__codex__codex` 호출마다 Codex를 읽기 전용으로 고정하고 Codex 자체 플러그인·`node_repl`을 끈다.
이 템플릿에서 Codex 호출 경로는 MCP `codex`뿐이다(2026-09-26 — Bash `codex exec` 경로와 그 판별
로직은 삭제).

왜 필요한가: `codex exec`와 달리 MCP `codex`는 `sandbox`를 생략하면 `workspace-write`·`on-request`로
열린다. 이 프로젝트의 Codex 역할은 "리뷰 전담"이라 쓰기 권한이 필요한 호출이 없으므로, 이 훅이
호출마다 `sandbox=read-only`, `approval-policy=never`를 덮어쓴다(사용자가 다른 값을 넘겨도
되돌린다). 또 `codex mcp-server`는 서버 시작 인자(`-c`)를 세션 설정에 반영하지 않고 호출 단위
`config`만 쓰므로(2026-09-21 실측), `tool_input.config`에 플러그인·`node_repl` 차단 값을 주입한다.
사용자가 넘긴 다른 `config` 값은 유지한다.

다른 훅과 달리 **제안이 아니라 입력을 고치는 훅**이다. `updatedInput`만 반환하고
`permissionDecision`은 내지 않으므로 권한 흐름(승인 프롬프트)은 그대로다.

입력이 예상과 다르면 통과시키지 않고 종료 코드 2로 호출을 막는다(fail-closed). 훅이 조용히 실패해
플러그인이 켜지거나 쓰기 권한이 열린 채 호출되는 것보다 호출이 막히는 쪽이 의도에 맞다.
한계: 훅 프로세스가 아예 못 뜨는 경우(python 없음·시간 초과)는 막을 수 없다. 그래서 호출할 때도
`sandbox: read-only`, `approval-policy: never`를 직접 적는다. `mcp__codex__codex-reply`는 훅 대상이
아니지만 세션 시작 때의 설정을 그대로 이어받는다(2026-09-22 실측: read-only·never·플러그인 없음).
"""

import json
import sys
from typing import Any

FORCED_CONFIG: dict[str, Any] = {
    "features.plugins": False,
    "mcp_servers.node_repl.enabled": False,
}
FORCED_PARAMS: dict[str, Any] = {
    "sandbox": "read-only",
    "approval-policy": "never",
}


def block(reason: str) -> None:
    print(
        f"codex-disable-plugins: {reason} — 읽기 전용·플러그인 차단 값을 주입하지 못해 "
        "호출을 막는다.",
        file=sys.stderr,
    )
    sys.exit(2)


def build_updated_input(tool_input: dict[str, Any]) -> dict[str, Any]:
    """강제 값(sandbox·approval-policy·config 차단 키)을 덮어쓴 tool_input을 돌려준다."""
    config = tool_input.get("config")
    if config is None:
        config = {}
    elif not isinstance(config, dict):
        raise TypeError("tool_input.config가 객체가 아니다")
    return {**tool_input, **FORCED_PARAMS, "config": {**config, **FORCED_CONFIG}}


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        block(f"stdin JSON 파싱 실패({exc})")

    if not isinstance(data, dict):
        block("stdin 최상위 값이 객체가 아니다")

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        block("tool_input이 객체가 아니다")

    try:
        updated = build_updated_input(tool_input)
    except TypeError as exc:
        block(str(exc))

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "updatedInput": updated,
                }
            },
            ensure_ascii=False,
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        # 예기치 못한 오류(종료 코드 1)는 호출이 그대로 진행되므로 2로 바꿔 막는다
        block(f"예기치 못한 오류({type(exc).__name__}: {exc})")
