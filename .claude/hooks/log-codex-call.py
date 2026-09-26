#!/usr/bin/env python3
"""PreToolUse/PostToolUse/PostToolUseFailure hook (matcher: mcp__codex__.*).

Claude가 실제로 Codex를 호출하는 순간(제안이 아니라 실제 `mcp__codex__codex` 또는
`mcp__codex__codex-reply` 호출)을 기록한다. 차단하지 않으며, 로그만 남긴다. 로그를 읽는 시각화
도구가 이 이벤트로 "Codex가 리뷰 중"/"리뷰 완료" 상태와 토큰 사용량을 그린다.

2026-09-26: Codex 호출 경로를 Bash `codex exec`에서 MCP `codex`로 되돌리며 matcher를 `Bash`에서
`mcp__codex__.*`로 바꿨다. 명령 문자열을 shlex로 파싱해 `codex exec`를 골라내던 판별 로직(heredoc·
`env`·`timeout` 접두어 처리)은 더 이상 필요 없어 삭제했다 — MCP 도구 이름이 곧 판별 기준이다.
안전장치로 `tool_name`이 `mcp__codex__`로 시작하지 않으면 조용히 종료한다(matcher가 잘못 등록돼도
무관한 호출을 Codex 호출로 기록하지 않는다).

Codex 호출의 `agent` 값은 항상 `codex-detective` 하나로 고정한다. Codex에게 보낸 prompt 내용으로
리뷰가 보안/퍼포먼스 중점이었는지는 추정하되, agent를 나누는 대신 detail에 표시만 남긴다.

토큰 사용량 출처: `mcp__codex__codex(-reply)`의 tool_response에는 `threadId`와 `content`만 있고
사용량이 없다(훅에는 이 JSON이 문자열로 넘어온다 — 2026-09-26 실측, `_response_payload`
참고). 대신 Codex가 CODEX_HOME/sessions/YYYY/MM/DD/rollout-...-<threadId>.jsonl 에 자체
세션 로그를 남기며, 그 안의 payload.type == "token_count" 이벤트에 누적/최근 토큰 수와 실제
모델 컨텍스트 윈도우(model_context_window)가 들어 있다. 이 파일을 threadId로 찾아 파싱한다.
threadId는 외부(Codex 응답)에서 온 값이고 glob 패턴에 그대로 들어가므로 16진수·하이픈만 허용한다.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from _hooklog import as_dict, log_event, read_hook_input

# rollout 파일에 model_context_window가 없는 극히 드문 경우에만 쓰는 최후의 대체값.
CONTEXT_LIMIT_FALLBACK = 128_000

CODEX_TOOL_PREFIX = "mcp__codex__"
DEFAULT_AGENT_ID = "codex-detective"
SECURITY_KEYWORDS = (
    "보안",
    "security",
    "인증",
    "auth",
    "취약점",
    "vulnerability",
    "secret",
    "권한",
    "permission",
    "암호화",
    "crypto",
)
PERF_KEYWORDS = (
    "성능",
    "퍼포먼스",
    "perf",
    "performance",
    "지연",
    "latency",
    "최적화",
    "optimize",
    "benchmark",
    "속도",
)

FOCUS_LABELS = {"security": "🛡️ 보안 중점", "perf": "⏱️ 퍼포먼스 중점"}

_THREAD_ID_PATTERN = re.compile(r"[0-9a-fA-F-]+")


def is_codex_tool(tool_name: str) -> bool:
    return tool_name.startswith(CODEX_TOOL_PREFIX)


def classify_focus(tool_input: dict[str, Any]) -> str | None:
    """Codex에게 보낸 prompt 내용으로 이 리뷰가 보안/퍼포먼스 중점이었는지 추정한다.

    보안 키워드가 우선한다 — 보안 이슈를 성능 최적화 요청보다 놓치면 안 되므로.
    둘 다 없으면 None(범용 리뷰)을 반환한다.
    """
    text = " ".join(str(v) for v in tool_input.values() if isinstance(v, str)).lower()
    if any(keyword in text for keyword in SECURITY_KEYWORDS):
        return "security"
    if any(keyword in text for keyword in PERF_KEYWORDS):
        return "perf"
    return None


def build_detail(tool_name: str, focus: str | None) -> str:
    if focus is None:
        return tool_name
    return f"{FOCUS_LABELS[focus]} · {tool_name}"


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))


def _response_payload(tool_response: object) -> dict[str, Any]:
    """MCP tool_response를 dict로 정규화한다.

    Claude Code는 MCP 도구 결과를 훅에 세 가지 모양으로 넘길 수 있다(2026-09-26 실측: 문자열).
    - JSON 문자열: '{"threadId": "...", "content": "..."}'
    - dict: {"threadId": ..., "content": ...} 또는 {"structuredContent": {...}}
    - content 블록 목록: [{"type": "text", "text": '{"threadId": ...}'}]
    """
    if isinstance(tool_response, dict):
        nested = tool_response.get("structuredContent")
        return nested if isinstance(nested, dict) and "threadId" in nested else tool_response
    if isinstance(tool_response, list):
        for block in tool_response:
            text = as_dict(block).get("text")
            if isinstance(text, str):
                parsed = _response_payload(text)
                if parsed:
                    return parsed
        return {}
    if isinstance(tool_response, str):
        try:
            return _response_payload(json.loads(tool_response))
        except json.JSONDecodeError:
            return {}
    return {}


def extract_thread_id(tool_response: object) -> str | None:
    """tool_response에서 threadId를 뽑는다. 형식(16진수·하이픈)이 아니면 무시한다."""
    thread_id = _response_payload(tool_response).get("threadId")
    if not isinstance(thread_id, str) or not thread_id:
        return None
    return thread_id if _THREAD_ID_PATTERN.fullmatch(thread_id) else None


def find_rollout_file(thread_id: str) -> Path | None:
    # thread_id는 외부(Codex 응답)에서 온 값이고 glob 패턴에 그대로 들어가므로 형식을 검증한다.
    if not _THREAD_ID_PATTERN.fullmatch(thread_id):
        return None
    sessions_dir = codex_home() / "sessions"
    if not sessions_dir.exists():
        return None
    matches = sorted(sessions_dir.glob(f"**/*-{thread_id}.jsonl"))
    return matches[-1] if matches else None


def extract_usage(thread_id: str) -> dict[str, Any] | None:
    rollout_path = find_rollout_file(thread_id)
    if rollout_path is None:
        return None

    latest_info = None
    try:
        with rollout_path.open(encoding="utf-8") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                payload = as_dict(entry.get("payload"))
                if payload.get("type") == "token_count":
                    latest_info = payload.get("info")
    except OSError:
        return None

    if not isinstance(latest_info, dict) or not latest_info:
        return None

    total = as_dict(latest_info.get("total_token_usage"))
    last = as_dict(latest_info.get("last_token_usage"))
    return {
        "input": total.get("input_tokens", 0),
        "output": total.get("output_tokens", 0),
        "total": total.get("total_tokens", 0),
        "context": last.get("total_tokens", 0),
        "limit": latest_info.get("model_context_window") or CONTEXT_LIMIT_FALLBACK,
    }


def main() -> None:
    data = read_hook_input()

    hook_event = str(data.get("hook_event_name", ""))
    tool_name = str(data.get("tool_name", ""))
    if not is_codex_tool(tool_name):
        sys.exit(0)

    tool_input = as_dict(data.get("tool_input"))
    detail = build_detail(tool_name, classify_focus(tool_input))

    if hook_event == "PreToolUse":
        log_event(
            "codex-invoke",
            "PreToolUse",
            triggered=True,
            detail=detail,
            agent=DEFAULT_AGENT_ID,
            status="working",
        )
        sys.exit(0)

    tool_response = data.get("tool_response")

    # 실패/중단 판정: PostToolUseFailure는 hook_event 자체가 알려주고, MCP 도구 응답은 is_error를,
    # 훅 payload 최상위는 is_interrupt를 실어 보낼 수 있다.
    failed = (
        hook_event == "PostToolUseFailure"
        or bool(data.get("is_interrupt"))
        or bool(as_dict(tool_response).get("is_error"))
    )

    usage_payload: dict[str, Any] | None = None
    try:
        thread_id = extract_thread_id(tool_response)
        if thread_id:
            usage_payload = extract_usage(thread_id)
    except Exception:
        # 파싱이 어떤 이유로든 실패해도 "Codex 호출이 끝났다"는 로그 자체는 남긴다.
        pass

    log_event(
        "codex-invoke",
        hook_event or "PostToolUse",
        triggered=True,
        detail=detail,
        agent=DEFAULT_AGENT_ID,
        status="fail" if failed else "ok",
        usage=usage_payload,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
