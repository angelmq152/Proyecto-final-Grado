from datetime import datetime

import pytest

from lobster_agent.agent.tools.dummy import echo, get_time, simple_calc


def test_get_time_returns_iso_datetime() -> None:
    result = get_time()

    assert "now" in result
    datetime.fromisoformat(result["now"])


def test_echo_returns_text() -> None:
    assert echo("hola") == {"echoed": "hola"}


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("1 + 2", 3.0),
        ("2 * (3 + 4)", 14.0),
        ("10 / 2", 5.0),
        ("-3 + 5", 2.0),
    ],
)
def test_simple_calc_valid_expressions(expr: str, expected: float) -> None:
    assert simple_calc(expr) == {"result": expected}


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('id')",
        "open('/etc/passwd').read()",
        "2 ** 8",
        "[1, 2, 3]",
    ],
)
def test_simple_calc_rejects_unsafe_expressions(expr: str) -> None:
    with pytest.raises(ValueError):
        simple_calc(expr)
