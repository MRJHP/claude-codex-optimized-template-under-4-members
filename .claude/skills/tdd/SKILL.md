---
name: tdd
description: 테스트 주도 개발(Red-Green-Refactor)로 기능을 구현하거나 버그를 수정한다. "TDD로 해줘", "테스트부터 작성해줘", 버그 수정 작업에 사용한다.
---

# tdd

[testing.md](../../rules/testing.md)의 AAA 패턴, 80% 커버리지 기준과 함께 사용한다.

## Red-Green-Refactor

1. **Red**: 원하는 동작(또는 재현하려는 버그)을 검증하는 테스트를 먼저 작성한다. `uv run pytest`로 실패하는
   것을 확인한다.
2. **Green**: 테스트를 통과시키는 **최소한의** 코드를 작성한다. 이 단계에서는 완벽함보다 통과가 목표다.
3. **Refactor**: 테스트가 통과하는 상태를 유지하면서 코드를 정리한다 ([coding-principles.md](../../rules/coding-principles.md)
   기준). 매 변경 후 `uv run pytest`로 여전히 통과하는지 확인한다.

## 버그 수정 시

1. 버그를 재현하는 테스트를 먼저 작성한다 (실패해야 정상).
2. 원인을 찾아 최소한으로 수정한다.
3. 테스트가 통과하는지 확인하고, 관련된 다른 테스트도 함께 돌려 회귀가 없는지 확인한다.
4. 같은 버그를 2회 이상 수정 시도해도 원인을 못 찾으면 [codex-delegation.md](../../rules/codex-delegation.md)
   기준에 따라 Codex에게 실패 로그와 관련 코드를 공유하고 분석을 요청한다.

## 커밋 전

`uv run ruff check . --fix && uv run ruff format . && uv run mypy . && uv run pytest` 모두 통과해야 한다
([dev-environment.md](../../rules/dev-environment.md)).
