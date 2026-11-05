"""muscle — the agent knows your shell.

Hermes can read a file you hand it, but it has no memory of the commands you have
actually typed: the ffmpeg invocation you worked out last month, the exact
systemctl sequence that restarts your blog, the curl with the odd header, the cd
into the directory where the tests pass. That knowledge sits in your shell
history, in plain text, unread.

``muscle`` indexes the history files and rc files that already exist — bash,
zsh and fish formats, aliases and functions — into a local SQLite/FTS5 index and
gives the agent five tools to search it. No capture daemon, no shell wrapper, no
account, no network. Secrets are redacted before anything is stored, and
``/muscle forget`` deletes the index.

Surfaces:

* ``shell_recall`` / ``shell_show`` / ``shell_last`` — find a command, open it
  in full with the commands around it, or see what ran recently.
* ``shell_habits`` — how the user actually works: repeated commands, programs,
  aliases and functions.
* ``shell_index`` — index or rebuild explicitly (normally automatic).
* ``/muscle`` — status, search, last, index, preview, forget, pause.
* A bundled skill — when shell memory beats guessing or asking.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from . import commands, db, ingest, render, schemas, tools
from .settings import PLUGIN_ID, SCHEMA_KEYS, Settings

logger = logging.getLogger(__name__)

_CTX: Any = None
_CACHED: Settings | None = None
_CACHED_AT = 0.0
_CACHE_SECONDS = 2.0
_STARTED = False


def current_settings() -> Settings:
    global _CACHED, _CACHED_AT
    now = time.monotonic()
    if _CACHED is not None and now - _CACHED_AT < _CACHE_SECONDS:
        return _CACHED
    _CACHED = Settings.from_ctx(_CTX) if _CTX is not None else Settings()
    _CACHED_AT = now
    return _CACHED


def register(ctx: Any) -> None:
    global _CTX, _STARTED

    _CTX = ctx
    settings = current_settings()

    handlers = {
        "shell_recall": tools.shell_recall,
        "shell_show": tools.shell_show,
        "shell_last": tools.shell_last,
        "shell_habits": tools.shell_habits,
        "shell_index": tools.shell_index,
    }
    for schema in schemas.ALL:
        ctx.register_tool(
            name=schema["name"],
            toolset="muscle",
            schema=schema,
            handler=handlers[schema["name"]],
        )

    ctx.register_command(
        "muscle",
        commands.handle,
        description="Your shell history, searchable by the agent",
    )

    skill_dir = Path(__file__).parent / "skills" / "muscle"
    if (skill_dir / "SKILL.md").is_file():
        try:
            ctx.register_skill("muscle", str(skill_dir))
        except Exception:  # pragma: no cover - optional surface
            logger.debug("muscle: could not register bundled skill", exc_info=True)

    if settings.enabled and settings.auto_index and not _STARTED:
        _STARTED = True
        ingest.background_index(settings)

    logger.info(
        "muscle ready: %s history files, redact=%s",
        len(settings.files),
        "on" if settings.redact else "off",
    )


__all__ = ["register", "current_settings", "PLUGIN_ID", "SCHEMA_KEYS", "db", "render"]
