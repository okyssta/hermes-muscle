"""/muscle — status, search, last, index, forget.

A slash command is the surface a person reaches for, so it answers in sentences.
It runs in the gateway process and returns text; the only state it changes is this
plugin's index and its own enabled flag.
"""

from __future__ import annotations

from typing import Any

from . import db, render
from .settings import Settings


def _settings() -> Settings:
    from . import current_settings

    return current_settings()


def _set(key: str, value: Any) -> None:
    from . import _CTX

    setter = getattr(_CTX, "set_config", None)
    if callable(setter):
        setter(key, value)


_HELP = """\
/muscle                      status: index size, files, redaction
/muscle search <words>       find a command you ran before
/muscle last [n]             the most recent commands
/muscle index                index new history entries (incremental)
/muscle reindex              drop and rebuild the whole index
/muscle preview              what is stored, and where it came from
/muscle forget               how many records would be removed
/muscle forget confirm       remove every record from the index
/muscle pause | resume       stop / restart indexing and lookups
"""


def handle(raw_args: str = "", **kwargs: Any) -> str:
    text = (raw_args or "").strip()
    lowered = text.lower()
    settings = _settings()

    if lowered in {"", "status", "stats"}:
        return render.status(settings)
    if lowered in {"help", "?"}:
        return _HELP

    if lowered.startswith("search ") or lowered.startswith("find "):
        query = text.split(" ", 1)[1].strip()
        from . import tools

        return tools.shell_recall({"query": query, "limit": 10})

    if lowered == "last" or lowered.startswith("last "):
        from . import tools

        parts = text.split()
        limit = 8
        if len(parts) > 1:
            try:
                limit = max(1, min(40, int(parts[1])))
            except ValueError:
                limit = 8
        return tools.shell_last({"limit": limit})

    if lowered in {"index", "scan", "sync", "reindex", "rebuild"}:
        from . import tools

        return tools.shell_index({"rebuild": lowered in {"reindex", "rebuild"}})

    if lowered.startswith("forget"):
        target = text[6:].strip().lower()
        stats = db.stats()
        if target != "confirm":
            return (
                f"forget would remove {stats['total']:,} records from the index at {stats['path']}.\n"
                "The history files themselves are never modified. Run `/muscle forget confirm` to proceed."
            )
        removed = db.forget()
        return (
            f"forgotten: {removed:,} records removed and the index vacuumed. "
            "Your history files are untouched."
        )

    if lowered.startswith("pause"):
        _set("enabled", False)
        return "muscle paused: no indexing and no lookups until /muscle resume."
    if lowered.startswith("resume"):
        _set("enabled", True)
        return "muscle resumed."

    if lowered == "preview":
        stats = db.stats()
        lines = [
            render.status(settings),
            "",
            "last records stored (secrets already redacted):",
        ]
        for row in db.recent(5):
            lines.append("  " + render.result_line(row, show_uses=False))
        aliases = db.definitions("alias", 5)
        if aliases:
            lines.append("")
            lines.append("aliases stored: " + ", ".join(row["name"] for row in aliases))
        return "\n".join(lines)

    # Anything else is treated as a search, which is what people type.
    from . import tools

    return tools.shell_recall({"query": text, "limit": 10})
