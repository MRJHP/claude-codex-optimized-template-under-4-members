# 테스트 규칙

## TDD

- 가능하면 실패하는 테스트를 먼저 작성하고(Red), 최소한의 코드로 통과시킨 뒤(Green), 리팩토링한다(Refactor).
- 버그를 고칠 때는 먼저 그 버그를 재현하는 테스트를 추가한다.
- 자세한 워크플로우는 [.claude/skills/tdd/SKILL.md](../skills/tdd/SKILL.md) 참고.

## AAA 패턴

모든 테스트는 Arrange / Act / Assert 세 구간으로 구성한다.

```python
def test_order_total_includes_tax():
    # Arrange
    order = Order(items=[Item(price=100)], tax_rate=0.1)

    # Act
    total = order.total()

    # Assert
    assert total == 110
```

- 한 테스트에서 여러 동작을 검증하지 않는다. 테스트 이름은 "무엇을 하면 무엇이 되어야 하는지"를 드러낸다.
- 외부 I/O(네트워크, 파일시스템, 시간)는 픽스처/mock으로 격리한다.

## 커버리지

- 최소 커버리지 목표는 **80%** (`pyproject.toml`의 `--cov-fail-under=80`).
- 커버리지 숫자를 채우기 위한 무의미한 테스트는 지양한다. 중요한 분기(에러 처리, 경계값)를 우선한다.
