"""Run a snippet of JSON handling in Node, jq, PHP or PostgreSQL, return stdout."""
import os
import subprocess

PG_CONTAINER = os.environ.get("LAB_PG_CONTAINER", "json-vs-lab-002")


def _run(cmd: list[str], stdin: str = "") -> str:
    done = subprocess.run(cmd, input=stdin, capture_output=True, text=True)
    return (done.stdout + done.stderr).strip()


def node(script: str, stdin: str = "") -> str:
    """Run a Node script; the document arrives on stdin."""
    return _run(["node", "-e", script], stdin)


def jq(program: str, stdin: str) -> str:
    return _run(["jq", "-c", program], stdin)


def php(script: str, stdin: str = "") -> str:
    return _run(["php", "-r", script], stdin)


def psql(sql: str, stdin: str = "") -> str:
    """One statement against the lab container; errors come back as text."""
    return _run(["docker", "exec", "-i", PG_CONTAINER, "psql", "-U",
                 "postgres", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
                stdin)


def versions() -> str:
    parts = [
        _run(["python3", "--version"]),
        "Node " + _run(["node", "--version"]),
        _run(["jq", "--version"]),
        _run(["php", "-r", "echo 'PHP ', PHP_VERSION;"]),
        "PostgreSQL " + psql("SHOW server_version"),
    ]
    return ", ".join(parts)
