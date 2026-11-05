"""Shared harness: a throwaway HERMES_HOME and a fake plugin context."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HERMES_SRC = Path(os.environ.get("HERMES_SRC", "/root/.hermes/hermes-agent"))


def pytest_configure(config):
    for path in (str(REPO_ROOT.parent), str(HERMES_SRC)):
        if path not in sys.path:
            sys.path.insert(0, path)


class FakeCtx:
    def __init__(self, config: dict | None = None):
        self.config = dict(config or {})
        self.set_calls: list[tuple[str, object]] = []

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def set_config(self, key, value):
        self.config[key] = value
        self.set_calls.append((key, value))


@pytest.fixture()
def home(tmp_path, monkeypatch):
    home = tmp_path / "hermes-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    import muscle.db as db

    db.close()
    yield home
    db.close()


@pytest.fixture()
def configure(home, monkeypatch):
    """Install a fake ctx; returns a function taking config kwargs."""

    import muscle

    def _configure(**kwargs):
        defaults = {"include_aliases": False, "include_functions": False, "auto_index": True}
        defaults.update(kwargs)
        ctx = FakeCtx(defaults)
        monkeypatch.setattr(muscle, "_CTX", ctx)
        monkeypatch.setattr(muscle, "_CACHED", None)
        monkeypatch.setattr(muscle.ingest, "_LAST_SCAN", 0.0)
        return ctx

    return _configure


@pytest.fixture()
def history(tmp_path):
    """A small bash history with timestamps, multi-line and a secret."""
    path = tmp_path / ".bash_history"
    now = 1_760_000_000
    lines = [
        f"#{now - 86400 * 30}",
        "cd ~/code/blog",
        f"#{now - 86400 * 29}",
        "git status",
        f"#{now - 86400 * 20}",
        "systemctl --user restart blog-web",
        f"#{now - 86400 * 10}",
        "ffmpeg -i talk.mp4 -vn -c:a libopus talk.opus",
        f"#{now - 86400 * 9}",
        "ffmpeg -i demo.mov -vn -c:a libopus demo.opus",
        f"#{now - 86400 * 8}",
        "export OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz012345",
        f"#{now - 86400 * 7}",
        "curl -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature' https://api.example.com/me",
        f"#{now - 86400 * 6}",
        "cd ~/code/api && pytest -q",
        f"#{now - 86400 * 5}",
        "git rebase -i HEAD~3",
        f"#{now - 86400 * 4}",
        "uv run pytest tests/test_auth.py -q",
        f"#{now - 86400 * 3}",
        "cd ~/code/blog",
        f"#{now - 86400 * 2}",
        "systemctl --user restart blog-web",
        f"#{now - 86400 * 1}",
        "ffmpeg -i talk.mp4 -vn -c:a libopus talk.opus",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture()
def rc(tmp_path):
    path = tmp_path / ".bashrc"
    path.write_text(
        "\n".join(
            [
                "alias gs='git status --short --branch'",
                "alias blog='cd ~/code/blog && git pull'",
                "deploy() {",
                "  git push origin main",
                "  ssh blog 'systemctl --user restart blog-web'",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path
