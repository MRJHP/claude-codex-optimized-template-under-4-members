"""모든 hook이 공유하는 실행 로그 유틸리티.

각 hook은 자기 판단(제안할지 말지)을 내린 뒤 이 함수로 결과를 한 줄만 기록한다.
로그는 차단/실패를 유발하면 안 되므로 쓰기 실패는 조용히 무시한다.

`agent`/`status`는 agent-visualizer(하네스 이벤트를 실시간 시각화하는 별도 도구)가
소비하는 필드다. 이 파일은 그 도구를 몰라도 되지만, 필드 이름은 계약으로 유지한다.
"""

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "hooks.jsonl"
REMINDER_STATE_DIR = Path(tempfile.gettempdir()) / "claude-codex-hook-reminders"


def log_event(
    hook_name: str,
    event: str,
    triggered: bool,
    detail: str = "",
    agent: str = "claude",
    status: str = "",
    usage: dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "hook": hook_name,
        "event": event,
        "triggered": triggered,
        "detail": detail,
        "agent": agent,
        "status": status or ("flag" if triggered else "working"),
        "usage": usage,
    }
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def already_suggested(session_id: str, hook_name: str) -> bool:
    """이 세션에서 hook_name이 이미 제안 메시지를 출력했다면 True, 아니면 기록하고 False.

    check-codex-before-write / check-codex-after-plan / post-implementation-review가
    같은 세션에서 파일마다 반복 출력해 알림 피로를 주는 것을 막는다(hook_name별로 세션당
    최초 1회만 출력 — 3개 hook은 각자 독립적으로 1회씩 가능). session_id가 없으면(테스트 등)
    억제하지 않고 항상 False를 반환한다.

    (session_id, hook_name) 쌍마다 별도 마커 파일을 `os.O_CREAT | os.O_EXCL`로 배타 생성한다 —
    공유 JSON 파일에 read-modify-write를 하면 두 hook이 동시에 실행될 때 서로의 기록을 덮어써
    dedup이 깨질 수 있다는 Codex 리뷰 지적을 반영해, 파일 생성 자체의 원자성에만 의존하도록
    단순화했다.
    """
    if not session_id:
        return False

    REMINDER_STATE_DIR.mkdir(parents=True, exist_ok=True)
    marker = REMINDER_STATE_DIR / f"{session_id}__{hook_name}.marker"
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return False
    except FileExistsError:
        return True
    except OSError:
        return False
