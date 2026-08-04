#!/usr/bin/env python3
"""PreToolUse/PostToolUse hook (matcher: mcp__codex__.*).

Claude가 실제로 Codex를 호출하는 순간(제안이 아니라 실제 호출)을 기록한다.
차단하지 않으며, 로그만 남긴다. agent-visualizer가 이 이벤트로 "Codex가 리뷰
중"/"리뷰 완료" 상태와 토큰 사용량을 그린다.

agent-visualizer의 Codex 쪽 캐릭터는 codex-detective 하나다(예전엔 탐정/보안 리뷰어/
퍼포먼스 리뷰어 3명으로 나눴었는데, 실제 로그를 보니 security/perf는 한 번도 발동한 적이
없어 늘 흑백으로 서 있기만 했다 — 2026-08-04 하나로 합침). Codex에게 보낸 prompt
내용으로 리뷰가 보안/퍼포먼스 중점이었는지는 여전히 추정하되, 캐릭터를 나누는 대신
detail(말풍선/카드/로그에 그대로 노출됨)에 표시만 남긴다.

토큰 사용량 출처: mcp__codex__codex(-reply)의 tool_response에는 {"threadId", "content"}만
있고 사용량이 없다 (실제 호출로 확인함). 대신 Codex CLI가 CODEX_HOME/sessions/YYYY/MM/DD/
rollout-...-<threadId>.jsonl 에 자체 세션 로그를 남기며, 그 안의
payload.type == "token_count" 이벤트에 누적/최근 토큰 수와 실제 모델 컨텍스트 윈도우
(model_context_window)가 들어 있다. 이 파일을 threadId로 찾아 파싱한다.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

from _hooklog import log_event

# rollout 파일에 model_context_window가 없는 극히 드문 경우에만 쓰는 최후의 대체값.
CONTEXT_LIMIT_FALLBACK = 128_000

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


def find_rollout_file(thread_id: str) -> Path | None:
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
                payload = entry.get("payload") or {}
                if payload.get("type") == "token_count":
                    latest_info = payload.get("info")
    except OSError:
        return None

    if not latest_info:
        return None

    total = latest_info.get("total_token_usage") or {}
    last = latest_info.get("last_token_usage") or {}
    return {
        "input": total.get("input_tokens", 0),
        "output": total.get("output_tokens", 0),
        "total": total.get("total_tokens", 0),
        "context": last.get("total_tokens", 0),
        "limit": latest_info.get("model_context_window") or CONTEXT_LIMIT_FALLBACK,
    }


def main() -> None:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        data = {}

    hook_event = str(data.get("hook_event_name", ""))
    tool_name = str(data.get("tool_name", "codex"))
    tool_input = data.get("tool_input", {}) or {}
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

    tool_response = data.get("tool_response", {}) or {}
    failed = hook_event == "PostToolUseFailure" or bool(tool_response.get("is_error"))
    status = "fail" if failed else "ok"

    thread_id = tool_response.get("threadId")
    usage_payload = extract_usage(thread_id) if thread_id else None

    log_event(
        "codex-invoke",
        hook_event or "PostToolUse",
        triggered=True,
        detail=detail,
        agent=DEFAULT_AGENT_ID,
        status=status,
        usage=usage_payload,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
