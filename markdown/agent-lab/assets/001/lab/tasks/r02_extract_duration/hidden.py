import ast
from pathlib import Path

import pytest

import trailhead
from trailhead.timefmt import format_duration

PACKAGE = Path(trailhead.__file__).parent


@pytest.mark.parametrize(
    ("hours", "text"),
    [
        (0, "0h 00m"),
        (0.75, "0h 45m"),
        (5.1167, "5h 07m"),
        (1.9999, "2h 00m"),
        (12, "12h 00m"),
        (30.5, "30h 30m"),
        (0.0083, "0h 00m"),
        (0.0084, "0h 01m"),
    ],
)
def test_format_duration(hours, text):
    assert format_duration(hours) == text


@pytest.mark.parametrize("module", ["plan.py", "report.py"])
def test_module_uses_the_shared_function(module):
    tree = ast.parse((PACKAGE / module).read_text())
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "format_duration" in names
    assert "divmod" not in names, f"{module} still formats durations itself"
