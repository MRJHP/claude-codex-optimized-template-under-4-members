"""`.claude/hooks/`의 회귀 테스트.

훅 파일명에 하이픈이 있어 일반 import가 안 되므로 경로로 로드한다. 로그(`hooks.jsonl`)와 dedup
마커는 tmp_path로 돌려 실제 저장소·임시 폴더를 오염시키지 않는다.

지키려는 계약:
- PreToolUse 훅(`check-codex-before-write`, `check-codex-after-plan`)은 `permissionDecision`을
  출력하지 않는다. `allow`를 내면 사용자 승인 없이 도구가 실행되는 권한 우회가 되고, 사유
  문구도 Claude에게 전달되지 않는다(2026-09-19 실험, Claude Code 2.1.278). 제안은
  `additionalContext`로만 전달한다.
- 세션당 1회 dedup: 두 번째부터는 아무것도 출력하지 않고, 로그에는 `status="working"`으로
  남긴다(기본값 `flag`면 시각화가 실제로 일어나지 않은 제안을 반복 표시한다).
- `codex-disable-plugins`는 `mcp__codex__codex` 호출마다 `sandbox=read-only`·
  `approval-policy=never`와 플러그인·`node_repl` 차단 `config`를 강제하고, 입력이 이상하면
  종료 코드 2로 호출을 막는다(fail-closed).
- `log-codex-call`은 `mcp__codex__*` 도구 호출만 기록하고, 그 외 입력에는 아무것도 하지 않는다.
"""

import importlib
import importlib.util
import io
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "hooks"

HookRunner = Callable[[str, dict[str, Any]], tuple[dict[str, Any] | None, list[dict[str, Any]]]]


def load_hook(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HOOKS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hooklog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    monkeypatch.syspath_prepend(str(HOOKS_DIR))
    module = importlib.import_module("_hooklog")
    monkeypatch.setattr(module, "LOG_PATH", tmp_path / "logs" / "hooks.jsonl")
    monkeypatch.setattr(module, "REMINDER_STATE_DIR", tmp_path / "markers")
    return module


@pytest.fixture
def run_hook(
    hooklog: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> HookRunner:
    def run(
        name: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """훅을 in-process로 실행해 (stdout JSON 또는 None, 이번 실행의 로그 항목들)을 돌려준다."""
        module = load_hook(name)
        log_path: Path = hooklog.LOG_PATH
        before = len(log_path.read_text(encoding="utf-8").splitlines()) if log_path.exists() else 0
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        capsys.readouterr()  # 이전 출력 비우기
        with pytest.raises(SystemExit) as excinfo:
            module.main()
        assert excinfo.value.code == 0
        out = capsys.readouterr().out.strip()
        lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
        entries = [json.loads(line) for line in lines[before:]]
        return (json.loads(out) if out else None), entries

    return run


def find_key(node: object, key: str) -> bool:
    """JSON 트리 어디에든 key가 있는지."""
    if isinstance(node, dict):
        return key in node or any(find_key(v, key) for v in node.values())
    if isinstance(node, list):
        return any(find_key(v, key) for v in node)
    return False


RISKY_WRITE = {
    "session_id": "s1",
    "tool_input": {"file_path": "src/auth/login.py", "content": "x"},
}
RISKY_PLAN = {
    "session_id": "s1",
    "tool_input": {"plan": "Add a database migration that will delete old rows."},
}


# ---------------------------------------------------------------------------
# PreToolUse 훅 — 권한 우회 금지, additionalContext로만 전달
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hook", "payload"),
    [("check-codex-before-write", RISKY_WRITE), ("check-codex-after-plan", RISKY_PLAN)],
)
def test_pretooluse_hook_suggests_via_additional_context_only(
    run_hook: HookRunner, hook: str, payload: dict[str, Any]
) -> None:
    # Arrange / Act
    output, _ = run_hook(hook, payload)

    # Assert
    assert output is not None
    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    assert "mcp__codex__codex" in specific["additionalContext"]
    assert not find_key(output, "permissionDecision")
    assert not find_key(output, "permissionDecisionReason")


@pytest.mark.parametrize(
    ("hook", "payload"),
    [
        (
            "check-codex-before-write",
            {"session_id": "s1", "tool_input": {"file_path": "README.md"}},
        ),
        (
            "check-codex-after-plan",
            {"session_id": "s1", "tool_input": {"plan": "rename a variable"}},
        ),
    ],
)
def test_pretooluse_hook_is_silent_when_not_risky(
    run_hook: HookRunner, hook: str, payload: dict[str, Any]
) -> None:
    output, entries = run_hook(hook, payload)

    assert output is None
    assert [e["triggered"] for e in entries] == [False]


@pytest.mark.parametrize(
    ("hook", "payload"),
    [("check-codex-before-write", RISKY_WRITE), ("check-codex-after-plan", RISKY_PLAN)],
)
def test_pretooluse_hook_survives_empty_or_invalid_stdin(
    hooklog: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    hook: str,
    payload: dict[str, Any],
) -> None:
    module = load_hook(hook)
    for raw in ("", "not json"):
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        with pytest.raises(SystemExit) as excinfo:
            module.main()
        assert excinfo.value.code == 0
    assert capsys.readouterr().out == ""


def test_no_hook_source_emits_a_permission_decision() -> None:
    """어떤 훅도 코드에서 permissionDecision 키를 만들지 않는다(설명용 백틱 언급은 제외)."""
    offenders = [
        path.name
        for path in sorted(HOOKS_DIR.glob("*.py"))
        if re.search(
            r"""["']permissionDecision(Reason)?["']\s*:""", path.read_text(encoding="utf-8")
        )
    ]
    assert offenders == []


# ---------------------------------------------------------------------------
# 세션당 1회 dedup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hook", "payload", "event"),
    [
        ("check-codex-before-write", RISKY_WRITE, "PreToolUse"),
        ("check-codex-after-plan", RISKY_PLAN, "PreToolUse"),
        ("post-implementation-review", RISKY_WRITE, "PostToolUse"),
    ],
)
def test_suggestion_is_emitted_once_per_session_and_deduped_is_logged_as_working(
    run_hook: HookRunner, hook: str, payload: dict[str, Any], event: str
) -> None:
    first_output, first_entries = run_hook(hook, payload)
    second_output, second_entries = run_hook(hook, payload)

    assert first_output is not None
    assert first_output["hookSpecificOutput"]["hookEventName"] == event
    assert first_entries[-1]["status"] == "flag"
    assert second_output is None
    assert second_entries[-1]["status"] == "working"
    assert "(deduped)" in second_entries[-1]["detail"]


def test_different_sessions_each_get_their_own_suggestion(run_hook: HookRunner) -> None:
    other = {**RISKY_WRITE, "session_id": "s2"}

    first, _ = run_hook("check-codex-before-write", RISKY_WRITE)
    second, _ = run_hook("check-codex-before-write", other)

    assert first is not None
    assert second is not None


def test_hooks_dedup_independently_of_each_other(run_hook: HookRunner) -> None:
    write_output, _ = run_hook("check-codex-before-write", RISKY_WRITE)
    review_output, _ = run_hook("post-implementation-review", RISKY_WRITE)

    assert write_output is not None
    assert review_output is not None


def test_already_suggested_without_session_id_never_suppresses(hooklog: ModuleType) -> None:
    assert hooklog.already_suggested("", "h") is False
    assert hooklog.already_suggested("", "h") is False


def test_already_suggested_first_false_then_true(hooklog: ModuleType) -> None:
    assert hooklog.already_suggested("sess", "h") is False
    assert hooklog.already_suggested("sess", "h") is True
    assert hooklog.already_suggested("sess", "other") is False


def test_already_suggested_survives_unwritable_marker_dir(
    hooklog: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """마커 디렉터리를 못 만들어도 예외가 전파되지 않고 dedup 없이(False) 제안 쪽으로 간다."""
    blocker = tmp_path / "blocker"
    blocker.write_text("file, not dir", encoding="utf-8")
    monkeypatch.setattr(hooklog, "REMINDER_STATE_DIR", blocker / "markers")

    assert hooklog.already_suggested("sess", "h") is False


def test_log_event_defaults_status_from_triggered(hooklog: ModuleType) -> None:
    hooklog.log_event("h", "PreToolUse", triggered=True)
    hooklog.log_event("h", "PreToolUse", triggered=False)
    hooklog.log_event("h", "PreToolUse", triggered=True, status="ok")

    lines = hooklog.LOG_PATH.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["status"] for line in lines] == ["flag", "working", "ok"]


# ---------------------------------------------------------------------------
# agent-router — 스킬 힌트 + 작업 유형별 에이전트(모델) 힌트
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("prompt", "agent", "model"),
    [
        ("src/auth 아래 파일 어디에 있어?", "explorer", "Haiku"),
        ("현황 정리해서 보여줘", "explorer", "Haiku"),
        ("로그인 버그 고쳐줘", "implementer", "Sonnet"),
        # 조사와 구현이 섞이면 구현
        ("설정 파일 찾아서 수정해줘", "implementer", "Sonnet"),
        ("캐시 구조를 어떻게 설계할까?", "architect", "Opus"),
        # 설계와 구현이 섞이면 설계
        ("아키텍처 바꿔줘", "architect", "Opus"),
        ("저장소 전부 점검해서 빠짐없이 확인해줘", "verifier", "Fable"),
        # 검증과 설계가 섞이면 검증
        ("설계 문서 전수 감사해줘", "verifier", "Fable"),
    ],
)
def test_agent_router_suggests_agent_and_model_by_task_type(
    run_hook: HookRunner, prompt: str, agent: str, model: str
) -> None:
    output, entries = run_hook("agent-router", {"session_id": "s1", "prompt": prompt})

    assert output is not None
    context = output["hookSpecificOutput"]["additionalContext"]
    assert f"`{agent}`({model})" in context
    assert "메인 세션 모델은 바뀌지 않" in context
    assert not find_key(output, "permissionDecision")
    assert f"{agent}({model})" in entries[-1]["detail"]


def test_agent_router_emits_skill_and_agent_hints_together(run_hook: HookRunner) -> None:
    output, entries = run_hook("agent-router", {"session_id": "s1", "prompt": "TDD로 버그 고쳐줘"})

    assert output is not None
    context = output["hookSpecificOutput"]["additionalContext"]
    assert "tdd" in context
    assert "`implementer`(Sonnet)" in context
    assert entries[-1]["detail"] == "tdd, implementer(Sonnet)"


def test_agent_router_is_silent_for_unrelated_prompt(run_hook: HookRunner) -> None:
    output, entries = run_hook("agent-router", {"session_id": "s1", "prompt": "안녕"})

    assert output is None
    assert [e["triggered"] for e in entries] == [False]


def test_agent_definitions_pin_models_per_rubric() -> None:
    """작업 유형별 에이전트의 frontmatter model이 CLAUDE.md 표와 일치한다."""
    agents_dir = HOOKS_DIR.parent / "agents"
    expected = {
        "explorer": "haiku",
        "implementer": "sonnet",
        "architect": "opus",
        "verifier": "fable",
        "pm": "sonnet",
    }
    for name, model in expected.items():
        text = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        frontmatter = text.split("---")[1]
        assert f"\nmodel: {model}\n" in frontmatter, name
        assert f"\nname: {name}\n" in frontmatter


# ---------------------------------------------------------------------------
# post-implementation-review / session-start-reminders
# ---------------------------------------------------------------------------


def test_post_implementation_review_uses_additional_context(run_hook: HookRunner) -> None:
    output, _ = run_hook("post-implementation-review", RISKY_WRITE)

    assert output is not None
    assert output["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "mcp__codex__codex" in output["hookSpecificOutput"]["additionalContext"]


def test_session_start_reminds_latest_changelog_heading(
    hooklog: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# CHANGELOG\n\n## 2099-01-01 (newest)\n\n## 2098-01-01 (older)\n", encoding="utf-8"
    )
    module = load_hook("session-start-reminders")
    monkeypatch.setattr(module, "CHANGELOG_PATH", changelog)

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code == 0
    context = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert "2099-01-01 (newest)" in context
    assert "2098-01-01" not in context


def test_session_start_is_silent_without_changelog(
    hooklog: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_hook("session-start-reminders")
    monkeypatch.setattr(module, "CHANGELOG_PATH", tmp_path / "missing.md")

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code == 0
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# codex-disable-plugins — mcp__codex__codex 호출을 읽기 전용·플러그인 차단으로 고정 (fail-closed)
# ---------------------------------------------------------------------------


def run_raw(
    name: str, raw: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int | None, str, str]:
    """훅을 원문 stdin으로 실행해 (종료 코드, stdout, stderr)를 돌려준다."""
    module = load_hook(name)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    capsys.readouterr()
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    captured = capsys.readouterr()
    code = excinfo.value.code
    return (code if isinstance(code, int) else None), captured.out, captured.err


CODEX_CALL = {
    "session_id": "s1",
    "hook_event_name": "PreToolUse",
    "tool_name": "mcp__codex__codex",
    "tool_input": {"prompt": "이 diff를 검토해줘"},
}


def test_disable_plugins_forces_read_only_and_blocks_plugins(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run_raw("codex-disable-plugins", json.dumps(CODEX_CALL), monkeypatch, capsys)

    assert code == 0
    output = json.loads(out)
    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "PreToolUse"
    updated = specific["updatedInput"]
    assert updated["prompt"] == "이 diff를 검토해줘"
    assert updated["sandbox"] == "read-only"
    assert updated["approval-policy"] == "never"
    assert updated["config"] == {
        "features.plugins": False,
        "mcp_servers.node_repl.enabled": False,
    }
    assert not find_key(output, "permissionDecision")


def test_disable_plugins_overrides_write_sandbox_but_keeps_user_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {
        **CODEX_CALL,
        "tool_input": {
            "prompt": "x",
            "sandbox": "workspace-write",
            "approval-policy": "on-request",
            "config": {"model": "gpt-5", "features.plugins": True},
        },
    }

    code, out, _ = run_raw("codex-disable-plugins", json.dumps(payload), monkeypatch, capsys)

    assert code == 0
    updated = json.loads(out)["hookSpecificOutput"]["updatedInput"]
    assert updated["sandbox"] == "read-only"
    assert updated["approval-policy"] == "never"
    assert updated["config"]["model"] == "gpt-5"
    assert updated["config"]["features.plugins"] is False
    assert updated["config"]["mcp_servers.node_repl.enabled"] is False


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not json",
        "[]",
        "null",
        json.dumps({"tool_input": "text"}),
        json.dumps({"tool_input": None}),
        json.dumps({**CODEX_CALL, "tool_input": {"prompt": "x", "config": "not-an-object"}}),
        json.dumps({**CODEX_CALL, "tool_input": {"prompt": "x", "config": [1, 2]}}),
    ],
)
def test_disable_plugins_fails_closed_on_unexpected_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], raw: str
) -> None:
    code, out, err = run_raw("codex-disable-plugins", raw, monkeypatch, capsys)

    assert code == 2
    assert out == ""
    assert "codex-disable-plugins" in err


# ---------------------------------------------------------------------------
# log-codex-call — MCP 도구 호출 기록·threadId 검증
# ---------------------------------------------------------------------------


@pytest.fixture
def codex_log(hooklog: ModuleType) -> ModuleType:
    return load_hook("log-codex-call")


def write_rollout(codex_home: Path, thread_id: str, *, window: int | None = 200_000) -> Path:
    sessions = codex_home / "sessions" / "2026" / "09" / "26"
    sessions.mkdir(parents=True)
    info: dict[str, Any] = {
        "total_token_usage": {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500},
        "last_token_usage": {"total_tokens": 900},
    }
    if window is not None:
        info["model_context_window"] = window
    lines = [
        "plain text line",
        json.dumps({"payload": {"type": "session_meta"}}),
        json.dumps({"payload": {"type": "token_count", "info": {"total_token_usage": {}}}}),
        json.dumps({"payload": {"type": "token_count", "info": info}}),
        "null",
    ]
    path = sessions / f"rollout-2026-09-26T00-00-00-{thread_id}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_log_codex_call_pretooluse_logs_working(run_hook: HookRunner) -> None:
    output, entries = run_hook("log-codex-call", CODEX_CALL)

    assert output is None
    assert len(entries) == 1
    assert entries[0]["hook"] == "codex-invoke"
    assert entries[0]["event"] == "PreToolUse"
    assert entries[0]["agent"] == "codex-detective"
    assert entries[0]["status"] == "working"
    assert entries[0]["detail"] == "mcp__codex__codex"


def test_log_codex_call_posttooluse_logs_ok_with_usage_from_rollout(
    run_hook: HookRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    thread_id = "019a5f2c-1234-abcd"
    write_rollout(tmp_path, thread_id)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    payload = {
        **CODEX_CALL,
        "hook_event_name": "PostToolUse",
        "tool_name": "mcp__codex__codex-reply",
        "tool_input": {"prompt": "보안 관점에서 다시 봐줘", "threadId": thread_id},
        "tool_response": {"threadId": thread_id, "content": "괜찮아 보인다"},
    }

    _, entries = run_hook("log-codex-call", payload)

    assert entries[-1]["event"] == "PostToolUse"
    assert entries[-1]["status"] == "ok"
    assert entries[-1]["detail"] == "🛡️ 보안 중점 · mcp__codex__codex-reply"
    assert entries[-1]["usage"] == {
        "input": 1200,
        "output": 300,
        "total": 1500,
        "context": 900,
        "limit": 200_000,
    }


def test_log_codex_call_uses_fallback_limit_when_rollout_has_no_window(
    codex_log: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_rollout(tmp_path, "abc123", window=None)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    usage = codex_log.extract_usage("abc123")

    assert usage is not None
    assert usage["limit"] == codex_log.CONTEXT_LIMIT_FALLBACK


@pytest.mark.parametrize(
    ("event", "response"),
    [
        ("PostToolUseFailure", {}),
        ("PostToolUse", {"is_error": True}),
    ],
)
def test_log_codex_call_logs_fail_on_failure_or_error(
    run_hook: HookRunner, event: str, response: dict[str, Any]
) -> None:
    payload = {**CODEX_CALL, "hook_event_name": event, "tool_response": response}

    _, entries = run_hook("log-codex-call", payload)

    assert entries[-1]["event"] == event
    assert entries[-1]["status"] == "fail"
    assert entries[-1]["usage"] is None


def test_log_codex_call_logs_fail_on_interrupt(run_hook: HookRunner) -> None:
    payload = {**CODEX_CALL, "hook_event_name": "PostToolUse", "is_interrupt": True}

    _, entries = run_hook("log-codex-call", payload)

    assert entries[-1]["status"] == "fail"


@pytest.mark.parametrize(
    "tool_name", ["Bash", "Edit", "mcp__other__codex", "codex", "", "mcp_codex_codex"]
)
def test_log_codex_call_ignores_non_codex_tools(run_hook: HookRunner, tool_name: str) -> None:
    payload = {**CODEX_CALL, "tool_name": tool_name}

    output, entries = run_hook("log-codex-call", payload)

    assert output is None
    assert entries == []


def test_classify_focus_prefers_security_over_perf(codex_log: ModuleType) -> None:
    assert codex_log.classify_focus({"prompt": "성능도 보고 인증 로직도 봐줘"}) == "security"
    assert codex_log.classify_focus({"prompt": "latency를 줄일 방법"}) == "perf"
    assert codex_log.classify_focus({"prompt": "네이밍만 봐줘", "sandbox": "read-only"}) is None
    assert codex_log.classify_focus({}) is None


@pytest.mark.parametrize(
    "response",
    [
        {"threadId": "019a-ABCdef-0123", "content": "x"},
        {"structuredContent": {"threadId": "019a-ABCdef-0123"}},
        # Claude Code가 훅에 넘기는 실제 모양(2026-09-26 실측): JSON 문자열
        '{"threadId":"019a-ABCdef-0123","content":"Sandbox mode: read-only"}',
        # MCP content 블록 목록
        [{"type": "text", "text": '{"threadId":"019a-ABCdef-0123","content":"x"}'}],
    ],
)
def test_extract_thread_id_accepts_hex_id_in_every_response_shape(
    codex_log: ModuleType, response: object
) -> None:
    assert codex_log.extract_thread_id(response) == "019a-ABCdef-0123"


def test_log_codex_call_reads_usage_when_response_is_json_string(
    run_hook: HookRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    thread_id = "01a0daf1-3e38-7573-825f-f2cd1bf717d4"
    write_rollout(tmp_path, thread_id)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    payload = {
        **CODEX_CALL,
        "hook_event_name": "PostToolUse",
        "tool_response": json.dumps({"threadId": thread_id, "content": "OK"}),
    }

    _, entries = run_hook("log-codex-call", payload)

    assert entries[-1]["status"] == "ok"
    assert entries[-1]["usage"]["total"] == 1500


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"threadId": None},
        {"threadId": ""},
        {"threadId": 123},
        {"threadId": "../../etc/*"},
        {"threadId": "abc def"},
        {"structuredContent": "text"},
        "not json",
        '"just a string"',
        [],
        [{"type": "text", "text": "plain"}],
        None,
        5,
    ],
)
def test_extract_thread_id_rejects_missing_or_unsafe_ids(
    codex_log: ModuleType, response: object
) -> None:
    assert codex_log.extract_thread_id(response) is None


def test_find_rollout_file_rejects_glob_metacharacters(
    codex_log: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "rollout-abc123.jsonl").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    assert codex_log.find_rollout_file("abc123") == sessions / "rollout-abc123.jsonl"
    assert codex_log.find_rollout_file("*") is None
    assert codex_log.find_rollout_file("../abc123") is None


def test_log_codex_call_survives_unreadable_rollout(
    run_hook: HookRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """rollout 파싱이 어떤 이유로든 실패해도 '호출이 끝났다'는 로그는 남는다."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing"))
    payload = {
        **CODEX_CALL,
        "hook_event_name": "PostToolUse",
        "tool_response": {"threadId": "abc123"},
    }

    _, entries = run_hook("log-codex-call", payload)

    assert entries[-1]["status"] == "ok"
    assert entries[-1]["usage"] is None


# ---------------------------------------------------------------------------
# 리뷰 지적 회귀: session_id 경로 조작 / 객체가 아닌 JSON 입력
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "session_id", ["../../escape", r"..\..\escape", "a/b", "/abs/path", "x" * 500, "세션-한글"]
)
def test_already_suggested_never_writes_outside_marker_dir(
    hooklog: ModuleType, tmp_path: Path, session_id: str
) -> None:
    before = {p for p in tmp_path.rglob("*")}

    assert hooklog.already_suggested(session_id, "h") is False
    assert hooklog.already_suggested(session_id, "h") is True

    created = {p for p in tmp_path.rglob("*")} - before
    marker_dir: Path = hooklog.REMINDER_STATE_DIR
    assert created
    assert all(p == marker_dir or marker_dir in p.parents for p in created)
    assert all(p.name.endswith(".marker") for p in created if p.is_file())


def test_already_suggested_distinguishes_similar_session_and_hook_pairs(
    hooklog: ModuleType,
) -> None:
    """('a', 'b__c')와 ('a__b', 'c')처럼 이어 붙이면 같아지는 쌍이 서로의 dedup을 가로채면 안 됨."""
    assert hooklog.already_suggested("a", "b__c") is False
    assert hooklog.already_suggested("a__b", "c") is False


@pytest.mark.parametrize("raw", ["[]", "null", '"text"', "123", "true"])
@pytest.mark.parametrize(
    "hook",
    [
        "check-codex-before-write",
        "check-codex-after-plan",
        "post-implementation-review",
        "post-test-analysis",
        "agent-router",
        "log-codex-call",
    ],
)
def test_hooks_survive_valid_json_that_is_not_an_object(
    hooklog: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    hook: str,
    raw: str,
) -> None:
    module = load_hook(hook)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code in (0, None)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("bad_tool_input", [[], "text", 5, None])
@pytest.mark.parametrize(
    "hook",
    [
        "check-codex-before-write",
        "post-implementation-review",
        "post-test-analysis",
        "log-codex-call",
    ],
)
def test_hooks_survive_non_object_tool_input(
    hooklog: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    hook: str,
    bad_tool_input: object,
) -> None:
    module = load_hook(hook)
    payload = json.dumps(
        {
            "session_id": "s",
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__codex__codex",
            "tool_input": bad_tool_input,
            "tool_response": bad_tool_input,
        }
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code in (0, None)
    assert capsys.readouterr().out == ""
