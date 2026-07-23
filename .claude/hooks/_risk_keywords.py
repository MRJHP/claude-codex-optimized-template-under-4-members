"""check-codex-before-write.py와 post-implementation-review.py가 공유하는 위험 경로 키워드."""

RISK_PATH_KEYWORDS = (
    "auth",
    "login",
    "payment",
    "billing",
    "security",
    "migration",
    "schema",
    "crypto",
    "secret",
    "permission",
)
