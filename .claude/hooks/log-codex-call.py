#!/usr/bin/env python3
"""PreToolUse/PostToolUse/PostToolUseFailure hook (matcher: Bash).

Claude가 실제로 Codex를 호출하는 순간(제안이 아니라 실제 `codex exec` 실행)을 기록한다.
차단하지 않으며, 로그만 남긴다. 로그를 읽는 시각화 도구가 이 이벤트로 "Codex가 리뷰
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

Codex 호출의 `agent` 값은 항상 `codex-detective` 하나로 고정한다. Codex에게 보낸 prompt
내용으로 리뷰가 보안/퍼포먼스 중점이었는지는 추정하되, agent를 나누는 대신 detail에 표시만
남긴다.

판별 범위 (테스트로 고정): heredoc 본문(프롬프트)은 판별에서 제외하고(본문의 짝 없는 따옴표
때문에 shlex가 실패하지 않도록), `CODEX_HOME=... codex exec`·`timeout 300 codex exec` 같은 접두어는
건너뛰고 판별한다. stdout에서 얻은 thread_id는 16진수·하이픈만 허용하고 그 외에는 무시한다
(rollout 파일 glob 패턴에 그대로 쓰이므로).

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

from _hooklog import as_dict, log_event, read_hook_input

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

# heredoc 시작 마커(`<<EOF`, `<<-EOF`, `<<'EOF'`, `<< "EOF"`). here-string(`<<<`)은 제외한다.
_HEREDOC_START = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# timeout이 값을 따로 받는 옵션 (`--signal=KILL`처럼 `=`로 붙인 형태는 토큰 하나라 해당 없음).
_TIMEOUT_VALUE_OPTIONS = {"-s", "--signal", "-k", "--kill-after"}
_THREAD_ID_PATTERN = re.compile(r"[0-9a-fA-F-]+")
# env가 값을 따로 받는 옵션 (`--unset=VAR`처럼 `=`로 붙인 형태는 토큰 하나라 해당 없음).
_ENV_VALUE_OPTIONS = {"-u", "--unset", "-C", "--chdir", "-a", "--argv0"}
# `env -S "codex exec ..."`는 값 하나가 명령 전체(공백 분리 문자열)다 — 풀어서 다시 판별한다.
_ENV_SPLIT_OPTIONS = {"-S", "--split-string"}


def strip_heredoc_bodies(command: str) -> str:
    """heredoc 본문(프롬프트)과 here-string 인자를 명령 문자열에서 제거한다.

    codex-delegation.md가 권장하는 `codex exec ... - <<'CODEX_PROMPT'` 형태에서 프롬프트 본문에
    짝 없는 따옴표(예: don't)가 있으면 shlex.split이 실패해 Codex 호출이 로그에서 누락되므로,
    판별 전에 본문을 걷어낸다. 마커가 있는 줄의 나머지(`| tail` 등)와 종결자 이후 줄은 남긴다.
    """
    kept: list[str] = []
    delimiter: str | None = None
    for line in command.split("\n"):
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            continue
        here_string = line.find("<<<")
        if here_string != -1:
            line = line[:here_string]
        match = _HEREDOC_START.search(line)
        if match:
            delimiter = match.group(2)
            line = f"{line[: match.start()]} {line[match.end() :]}"
        kept.append(line)
    return "\n".join(kept)


def _skip_command_prefix(tokens: list[str]) -> list[str]:
    """`FOO=bar`·`env`·`timeout <옵션> <시간>` 접두어를 건너뛴 나머지 토큰을 반환한다."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        program = token.replace("\\", "/").rsplit("/", 1)[-1]
        if _ENV_ASSIGNMENT.match(token):
            index += 1
        elif program == "env":
            index += 1
            # `env -i FOO=1 codex exec`, `env -u VAR codex exec`, `env -- FOO=1 codex exec`처럼
            # env 자신의 옵션(과 그 값)을 건너뛴다. 뒤따르는 FOO=bar는 다음 반복이 처리한다.
            while index < len(tokens) and tokens[index].startswith("-") and tokens[index] != "-":
                option = tokens[index]
                if option == "--":
                    index += 1
                    break
                if option in _ENV_SPLIT_OPTIONS or option.startswith("--split-string="):
                    if option in _ENV_SPLIT_OPTIONS:
                        if index + 1 >= len(tokens):
                            return []
                        value, rest = tokens[index + 1], tokens[index + 2 :]
                    else:
                        value, rest = option.split("=", 1)[1], tokens[index + 1 :]
                    try:
                        expanded = shlex.split(value)
                    except ValueError:
                        return []
                    return _skip_command_prefix(expanded + rest)
                index += 2 if option in _ENV_VALUE_OPTIONS else 1
        elif program == "timeout":
            index += 1
            while index < len(tokens) and tokens[index].startswith("-"):
                index += 2 if tokens[index] in _TIMEOUT_VALUE_OPTIONS else 1
            index += 1  # 제한 시간(예: 300, 5m)
        else:
            break
    return tokens[index:]


def _segment_starts_with_codex_exec(segment: str) -> bool:
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        # 따옴표가 안 맞는 등 파싱 불가한 조각은 판단하지 않는다(오탐보다 누락이 안전).
        return False
    tokens = _skip_command_prefix(tokens)
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
    `codex -c x=1 exec ...`처럼 전역 옵션이 subcommand 앞에 오는 경우, `CODEX_HOME=... codex exec`·
    `timeout 300 codex exec` 같은 접두어가 붙은 경우, heredoc 프롬프트 본문에 짝 없는 따옴표가
    있는 경우도 잡아낸다.
    """
    command = strip_heredoc_bodies(command)
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
    # thread_id는 외부(Codex stdout)에서 온 값이고 glob 패턴에 그대로 들어가므로 형식을 검증한다.
    if not _THREAD_ID_PATTERN.fullmatch(thread_id):
        return None
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
    호출 자체의 성공/실패 로그는 남는다). 유일한 thread_id라도 16진수·하이픈 형식이 아니면
    (rollout 파일 glob 패턴에 쓰이므로) 무시한다.
    """
    ids = {
        str(e["thread_id"])
        for e in events
        if e.get("type") == "thread.started" and e.get("thread_id")
    }
    if len(ids) != 1:
        return None
    thread_id = next(iter(ids))
    return thread_id if _THREAD_ID_PATTERN.fullmatch(thread_id) else None


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
    data = read_hook_input()

    hook_event = str(data.get("hook_event_name", ""))
    tool_input = as_dict(data.get("tool_input"))
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

    tool_response = as_dict(data.get("tool_response"))
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
