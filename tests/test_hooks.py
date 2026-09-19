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
    assert "codex exec" in specific["additionalContext"]
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
# post-implementation-review / session-start-reminders
# ---------------------------------------------------------------------------


def test_post_implementation_review_uses_additional_context(run_hook: HookRunner) -> None:
    output, _ = run_hook("post-implementation-review", RISKY_WRITE)

    assert output is not None
    assert output["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "codex exec" in output["hookSpecificOutput"]["additionalContext"]


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
# log-codex-call — 호출 판별·thread_id 검증
# ---------------------------------------------------------------------------


@pytest.fixture
def codex_log(hooklog: ModuleType) -> ModuleType:
    return load_hook("log-codex-call")


@pytest.mark.parametrize(
    "command",
    [
        "codex exec --json --sandbox read-only -",
        "codex.cmd exec --json -",
        "codex -c model=x exec --json -",
        "CODEX_HOME=/tmp/x codex exec --json -",
        "env FOO=1 codex exec --json -",
        "timeout 300 codex exec --json -",
        "timeout -s KILL 300 codex exec --json -",
        "cd repo && codex exec --json -",
        # heredoc 프롬프트 본문에 짝 없는 따옴표가 있어도 판별에 실패하지 않는다.
        "codex exec --json --sandbox read-only - <<'CODEX_PROMPT'\ndon't break\nCODEX_PROMPT",
    ],
)
def test_is_codex_exec_command_true(codex_log: ModuleType, command: str) -> None:
    assert codex_log.is_codex_exec_command(command) is True


@pytest.mark.parametrize(
    "command",
    [
        'echo "codex exec"',
        'rg "codex exec" .',
        "codex login",
        "ls -la",
        "",
    ],
)
def test_is_codex_exec_command_false(codex_log: ModuleType, command: str) -> None:
    assert codex_log.is_codex_exec_command(command) is False


def test_strip_heredoc_bodies_keeps_command_line_and_text_after_terminator(
    codex_log: ModuleType,
) -> None:
    command = "codex exec - <<'EOF' | tail -5\nsecret body\nEOF\necho done"

    stripped = codex_log.strip_heredoc_bodies(command)

    assert "secret body" not in stripped
    assert "tail -5" in stripped
    assert "echo done" in stripped


def test_extract_thread_id_accepts_single_hex_id(codex_log: ModuleType) -> None:
    events = [{"type": "thread.started", "thread_id": "019a-ABCdef-0123"}]
    assert codex_log.extract_thread_id(events) == "019a-ABCdef-0123"


@pytest.mark.parametrize(
    "events",
    [
        [],
        [
            {"type": "thread.started", "thread_id": "aaaa"},
            {"type": "thread.started", "thread_id": "bbbb"},
        ],
        [{"type": "thread.started", "thread_id": "../../etc/*"}],
        [{"type": "thread.started", "thread_id": "abc def"}],
    ],
)
def test_extract_thread_id_rejects_ambiguous_or_unsafe_ids(
    codex_log: ModuleType, events: list[dict[str, Any]]
) -> None:
    assert codex_log.extract_thread_id(events) is None


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


def test_iter_json_lines_ignores_non_dict_and_garbage(codex_log: ModuleType) -> None:
    stdout = 'plain text\nnull\n[1, 2]\n{"type": "turn.completed"}\n\n'

    events = codex_log._iter_json_lines(stdout)

    assert events == [{"type": "turn.completed"}]


# ---------------------------------------------------------------------------
# 리뷰 지적 회귀: session_id 경로 조작 / 객체가 아닌 JSON 입력 / env 옵션
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
    "hook", ["check-codex-before-write", "post-implementation-review", "post-test-analysis"]
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
        {"session_id": "s", "tool_input": bad_tool_input, "tool_response": bad_tool_input}
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

    with pytest.raises(SystemExit) as excinfo:
        module.main()

    assert excinfo.value.code in (0, None)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "command",
    [
        "env -i CODEX_HOME=/tmp/x codex exec --json -",
        "env -u OPENAI_API_KEY codex exec --json -",
        "env --unset=FOO codex exec --json -",
        "env -C /tmp codex exec --json -",
        "env -- FOO=1 codex exec --json -",
        "env -i -u A -u B FOO=1 timeout 60 codex exec --json -",
    ],
)
def test_is_codex_exec_command_handles_env_options(codex_log: ModuleType, command: str) -> None:
    assert codex_log.is_codex_exec_command(command) is True


@pytest.mark.parametrize(
    "command",
    ["env -i FOO=1 ls", "env -u X python script.py", "env", "env -i"],
)
def test_env_prefix_without_codex_is_not_a_codex_call(codex_log: ModuleType, command: str) -> None:
    assert codex_log.is_codex_exec_command(command) is False


@pytest.mark.parametrize(
    "command",
    [
        "env -S 'codex exec --json -'",
        "env --split-string='codex exec --json -'",
        "env -i -S 'FOO=1 codex exec --json -'",
        "env -a mycodex codex exec --json -",
        "env --argv0=x codex exec --json -",
    ],
)
def test_is_codex_exec_command_handles_env_split_string_and_argv0(
    codex_log: ModuleType, command: str
) -> None:
    assert codex_log.is_codex_exec_command(command) is True


@pytest.mark.parametrize(
    "command",
    [
        # -a의 값이 'codex'일 뿐 실제 실행 파일은 exec다 — Codex 호출이 아니다
        "env -a codex exec --json",
        "env -S 'ls -la'",
        "env -S",
        "env -S 'unterminated \"quote'",
    ],
)
def test_is_codex_exec_command_env_edge_cases_are_not_codex_calls(
    codex_log: ModuleType, command: str
) -> None:
    assert codex_log.is_codex_exec_command(command) is False
