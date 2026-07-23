"""모든 hook이 공유하는 실행 로그 유틸리티.

각 hook은 자기 판단(제안할지 말지)을 내린 뒤 이 함수로 결과를 한 줄만 기록한다.
로그는 차단/실패를 유발하면 안 되므로 쓰기 실패는 조용히 무시한다.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "hooks.jsonl"


def log_event(hook_name: str, event: str, triggered: bool, detail: str = "") -> None:
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "hook": hook_name,
        "event": event,
        "triggered": triggered,
        "detail": detail,
    }
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
