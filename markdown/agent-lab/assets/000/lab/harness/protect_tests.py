#!/usr/bin/env python3
"""PreToolUse hook: block Edit/Write on tests, test config and the guardrails themselves.

Exit code 2 blocks the tool call and shows stderr to the model.
"""
import json
import os
import sys

PROTECTED_DIRS = ("tests/", ".claude/")
PROTECTED_FILES = {"conftest.py", "pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini",
                   "CLAUDE.md"}

event = json.load(sys.stdin)
tool_input = event.get("tool_input", {})
path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
relative = os.path.relpath(os.path.abspath(path), root) if path else ""

if relative.startswith(PROTECTED_DIRS) or os.path.basename(relative) in PROTECTED_FILES:
    print(f"Blocked: {relative} is part of the test suite or its configuration. "
          "Fix the code under src/ instead.", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
