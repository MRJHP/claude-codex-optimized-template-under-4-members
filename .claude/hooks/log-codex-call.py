#!/usr/bin/env python3
"""PreToolUse/PostToolUse hook (matcher: mcp__codex__.*).

Claude가 실제로 Codex를 호출하는 순간(제안이 아니라 실제 호출)을 기록한다.
차단하지 않으며, 로그만 남긴다. agent-visualizer가 이 이벤트로 "Codex가 리뷰
중"/"리뷰 완료" 상태와 토큰 사용량을 그린다.

agent-visualizer의 캐릭터 로스터에는 Codex 쪽에 탐정/보안 리뷰어/퍼포먼스 리뷰어 3명이
있는데, 이 hook이 항상 "codex"(탐정으로 폴백)만 기록하면 나머지 둘은 영원히 대기 상태로
남는다. Codex에게 보낸 prompt 내용으로 리뷰 성격을 추정해 로스터 id를 직접 지정한다
(resolveAgentId는 entry.agent가 로스터 id와 정확히 일치하면 그대로 채택한다).

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


def classify_agent(tool_input: dict[str, Any]) -> str:
    """Codex에게 보낸 prompt 내용으로 담당 리뷰어 캐릭터를 고른다.

    보안 키워드가 우선한다 — 보안 이슈를 성능 최적화 요청보다 놓치면 안 되므로.
    둘 다 없으면 범용 리뷰(codex-detective)로 취급한다.
    """
    text = " ".join(str(v) for v in tool_input.values() if isinstance(v, str)).lower()
    if any(keyword in text for keyword in SECURITY_KEYWORDS):
        return "codex-security"
    if any(keyword in text for keyword in PERF_KEYWORDS):
        return "codex-perf"
    return DEFAULT_AGENT_ID


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
    agent_id = classify_agent(tool_input)

    if hook_event == "PreToolUse":
        log_event(
            "codex-invoke",
            "PreToolUse",
            triggered=True,
            detail=tool_name,
            agent=agent_id,
            status="working",
        )
        sys.exit(0)

    tool_response = data.get("tool_response", {}) or {}
    failed = bool(tool_response.get("is_error"))
    status = "fail" if failed else "ok"

    thread_id = tool_response.get("threadId")
    usage_payload = extract_usage(thread_id) if thread_id else None

    log_event(
        "codex-invoke",
        "PostToolUse",
        triggered=True,
        detail=tool_name,
        agent=agent_id,
        status=status,
        usage=usage_payload,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
