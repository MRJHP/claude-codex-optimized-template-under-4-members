#!/usr/bin/env python3
"""PreToolUse/PostToolUse/PostToolUseFailure hook (matcher: Bash).

Claude가 실제로 Codex를 호출하는 순간(제안이 아니라 실제 `codex exec` 실행)을 기록한다.
차단하지 않으며, 로그만 남긴다. agent-visualizer가 이 이벤트로 "Codex가 리뷰
중"/"리뷰 완료" 상태와 토큰 사용량을 그린다.

2026-09-12: Codex CLI 0.154.0에서 `codex mcp-server`가 삭제되며 `mcp__codex__codex` MCP 도구
자체가 사라졌다. Codex 호출은 이제 Bash의 `codex exec` 명령이라 matcher를 `Bash`로 바꿨고, 이
스크립트가 명령 문자열로 codex exec 호출만 걸러낸다(그 외 Bash 호출은 즉시 조용히 종료 —
`post-test-analysis.py`가 "pytest" 아닌 명령을 거르는 것과 같은 패턴).

**판별의 한계 (Codex 사후 리뷰로 확인, 2026-09-12)**: 명령 문자열 패턴 매칭이라 완벽하지 않다.
`echo "codex exec"`처럼 문자열만 언급한 경우, `false && codex exec ...`처럼 실제로는 실행되지
않는 경우까지 완전히 걸러내지는 못한다. 이 hook은 대시보드 시각화용 로그이지 실행을 막거나
보장하는 게 아니므로, 오탐/누락이 있어도 Codex 호출 자체에는 영향이 없다. 정확한 판별이
필요해지면(예: 과금 근거로 쓰는 경우) 공통 wrapper 스크립트로 옮기는 편이 낫다.

agent-visualizer의 Codex 쪽 캐릭터는 codex-detective 하나다(예전엔 탐정/보안 리뷰어/
퍼포먼스 리뷰어 3명으로 나눴었는데, 실제 로그를 보니 security/perf는 한 번도 발동한 적이
없어 늘 흑백으로 서 있기만 했다 — 2026-08-04 하나로 합침). Codex에게 보낸 prompt
내용으로 리뷰가 보안/퍼포먼스 중점이었는지는 여전히 추정하되, 캐릭터를 나누는 대신
detail(말풍선/카드/로그에 그대로 노출됨)에 표시만 남긴다.

토큰 사용량 출처: `codex exec`의 stdout(`--json` 필수)에서 `{"type":"thread.started",
"thread_id":...}` 이벤트로 thread_id를 얻는다. 사용량 자체(총합/컨텍스트 윈도우 한도 포함)는
CODEX_HOME/sessions/YYYY/MM/DD/rollout-...-<threadId>.jsonl 의 payload.type == "token_count"
이벤트가 더 상세해(model_context_window 포함) 기존과 동일하게 이 파일을 threadId로 찾아
파싱한다 — mcp__codex__codex 시절과 이 부분 로직은 바뀌지 않았다.
"""

import json
import os
import re
import shlex
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

# && / || / ; / | 로 명령을 분절한다 (완전한 셸 파서는 아니고, "codex exec가 첫 단어인 세그먼트가
# 있는지"를 보는 실용적 근사치다).
_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\|")

CODEX_EXECUTABLE_BASENAMES = {"codex", "codex.cmd", "codex.exe"}


def _segment_starts_with_codex_exec(segment: str) -> bool:
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        # 따옴표가 안 맞는 등 파싱 불가한 조각은 판단하지 않는다(오탐보다 누락이 안전).
        return False
    if not tokens:
        return False
    program = tokens[0].replace("\\", "/").rsplit("/", 1)[-1]
    if program not in CODEX_EXECUTABLE_BASENAMES:
        return False
    return "exec" in tokens[1:]


def is_codex_exec_command(command: str) -> bool:
    """명령 문자열에 `codex exec`를 실제로 실행하는 세그먼트가 있는지 판별한다.

    `echo "codex exec"`, `rg "codex exec" .`처럼 문자열만 언급한 경우는 shlex가 인용된
    "codex exec"를 토큰 하나로 묶어버려 첫 토큰이 "codex"가 되지 않으므로 걸러진다.
    `codex -c x=1 exec ...`처럼 전역 옵션이 subcommand 앞에 오는 경우는 잡아낸다.
    """
    return any(_segment_starts_with_codex_exec(seg) for seg in _SEGMENT_SPLIT.split(command))


def classify_focus(text: str) -> str | None:
    """Codex에게 보낸 prompt 내용으로 이 리뷰가 보안/퍼포먼스 중점이었는지 추정한다.

    보안 키워드가 우선한다 — 보안 이슈를 성능 최적화 요청보다 놓치면 안 되므로.
    둘 다 없으면 None(범용 리뷰)을 반환한다.
    """
    lowered = text.lower()
    if any(keyword in lowered for keyword in SECURITY_KEYWORDS):
        return "security"
    if any(keyword in lowered for keyword in PERF_KEYWORDS):
        return "perf"
    return None


def build_detail(focus: str | None) -> str:
    if focus is None:
        return "codex exec"
    return f"{FOCUS_LABELS[focus]} · codex exec"


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))


def find_rollout_file(thread_id: str) -> Path | None:
    sessions_dir = codex_home() / "sessions"
    if not sessions_dir.exists():
        return None
    matches = sorted(sessions_dir.glob(f"**/*-{thread_id}.jsonl"))
    return matches[-1] if matches else None


def _iter_json_lines(stdout: str) -> list[dict[str, Any]]:
    """stdout(JSONL)에서 dict 형태 이벤트만 뽑는다.

    `--json`이 빠져 일반 텍스트가 섞이거나, 한 줄이 dict가 아닌 값(null/list/숫자)이어도
    무시하고 넘어간다(예전에는 entry.get() 호출이 AttributeError로 죽어 종료 로그 자체가
    누락됐다 — Codex 사후 리뷰로 발견).
    """
    events: list[dict[str, Any]] = []
    for raw_line in stdout.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            entry = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            events.append(entry)
    return events


def extract_thread_id(events: list[dict[str, Any]]) -> str | None:
    """thread.started 이벤트에서 thread_id를 뽑는다.

    출력에 서로 다른 thread_id가 두 개 이상 섞여 있으면(여러 호출이 파이프 등으로 뒤섞인 경우)
    어느 쪽 사용량인지 확신할 수 없으므로 귀속시키지 않는다(None 반환 — usage는 생략되지만
    호출 자체의 성공/실패 로그는 남는다).
    """
    ids = {
        str(e["thread_id"])
        for e in events
        if e.get("type") == "thread.started" and e.get("thread_id")
    }
    if len(ids) == 1:
        return next(iter(ids))
    return None


def has_turn_completed(events: list[dict[str, Any]]) -> bool:
    return any(e.get("type") == "turn.completed" for e in events)


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
    tool_input = data.get("tool_input", {}) or {}
    command = str(tool_input.get("command", ""))

    if not is_codex_exec_command(command):
        sys.exit(0)

    detail = build_detail(classify_focus(command))

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
    stdout = str(tool_response.get("stdout", ""))

    # 실패/중단 판정: PostToolUseFailure는 hook_event 자체가 알려주고, Bash 도구는 중단 시
    # tool_response.interrupted를, 훅 payload 최상위에 is_interrupt를 실어 보낼 수 있다. 종료
    # 코드 필드명은 안정적으로 문서화되어 있지 않아 신뢰하지 않는다.
    failed = (
        hook_event == "PostToolUseFailure"
        or bool(data.get("is_interrupt"))
        or bool(tool_response.get("interrupted"))
    )

    events: list[dict[str, Any]] = []
    thread_id: str | None = None
    usage_payload: dict[str, Any] | None = None
    try:
        events = _iter_json_lines(stdout)
        thread_id = extract_thread_id(events)
        if thread_id:
            usage_payload = extract_usage(thread_id)
    except Exception:
        # 파싱이 어떤 이유로든 실패해도 "Codex 호출이 끝났다"는 로그 자체는 남긴다.
        pass

    if failed:
        status = "fail"
    elif has_turn_completed(events):
        status = "ok"
    else:
        # 명령은 실행됐지만 완료 증거(turn.completed)를 못 찾음 — 예: --json 누락, 백그라운드
        # 실행, 파이프로 출력이 다른 곳에 소비됨. "성공"으로 과신하지 않고 미확인으로 표시한다.
        status = "flag"

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
