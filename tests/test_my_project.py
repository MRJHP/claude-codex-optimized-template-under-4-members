from my_project import greet


def test_greet_returns_greeting_with_name() -> None:
    # Arrange
    name = "world"

    # Act
    result = greet(name)

    # Assert
    assert result == "Hello, world!"
