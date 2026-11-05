"""Tool handlers — never raise, always answer with text the model can act on."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta
from typing import Any

from . import db, ingest, render
from .settings import Settings

_RELATIVE = re.compile(
    r"^(?P<n>\d+)\s*(?P<unit>m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|week|weeks)$",
    re.I,
)


def get_settings() -> Settings:
    from . import current_settings

    return current_settings()


def parse_when(text: str | None, *, end: bool = False) -> float | None:
    if not text:
        return None
    value = str(text).strip().lower()
    if not value or value in {"any", "all", "anytime", "ever"}:
        return None
    now = time.time()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if value in {"now", "just now"}:
        return now
    if value == "today":
        return today.timestamp() if not end else now
    if value == "yesterday":
        start = today - timedelta(days=1)
        return start.timestamp() if not end else today.timestamp() - 1
    if value == "last week":
        return (today - timedelta(days=7)).timestamp()
    if value == "last month":
        return (today - timedelta(days=30)).timestamp()
    relative = _RELATIVE.match(value.replace("ago", "").strip())
    if relative:
        count = int(relative.group("n"))
        unit = relative.group("unit").lower()
        if unit.startswith("m"):
            delta = timedelta(minutes=count)
        elif unit.startswith("h"):
            delta = timedelta(hours=count)
        elif unit.startswith("d"):
            delta = timedelta(days=count)
        else:
            delta = timedelta(weeks=count)
        return (now - delta.total_seconds()) if not end else now
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if fmt in {"%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"}:
            start = parsed.replace(hour=0, minute=0, second=0)
            return start.timestamp() if not end else (start + timedelta(days=1)).timestamp() - 1
        return parsed.timestamp()
    return None


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _prepare(settings: Settings) -> None:
    try:
        ingest.ensure_indexed(settings)
    except Exception:
        pass


def shell_recall(args: dict | None = None, **kwargs: Any) -> str:
    data = args or {}
    query = str(data.get("query") or "").strip()
    if not query:
        return "Error: shell_recall needs a query — words from the command or what it did."
    settings = get_settings()
    if not settings.enabled:
        return "muscle is paused (enabled=false). The index is unchanged; re-enable it to search."
    _prepare(settings)
    since = parse_when(data.get("since"))
    until = parse_when(data.get("until"), end=True)
    limit = _int(data.get("limit"), 8, 1, 25)
    kinds = ("command", "alias", "function") if data.get("include_definitions") else ("command",)
    try:
        rows = db.search(query, limit=limit, since=since, until=until, kinds=kinds)
        total = db.stats()["total"]
    except Exception as exc:  # pragma: no cover - a tool must answer
        return f"Error: shell history search failed ({exc}). Try shell_index, then retry."
    return render.results(
        query,
        rows,
        total=total,
        since=str(data.get("since") or ""),
        until=str(data.get("until") or ""),
    )


def shell_show(args: dict | None = None, **kwargs: Any) -> str:
    data = args or {}
    try:
        entry_id = int(data.get("id"))
    except (TypeError, ValueError):
        return "Error: shell_show needs the numeric id shown as [#id]."
    try:
        row = db.get(entry_id)
        if row is None:
            return f"No command with id {entry_id}. Use shell_recall or shell_last to find one."
        before, after = db.neighbours(row)
        return render.record(row, before, after, db.uses(row["norm"]))
    except Exception as exc:  # pragma: no cover
        return f"Error: could not read command #{entry_id} ({exc})."


def shell_last(args: dict | None = None, **kwargs: Any) -> str:
    data = args or {}
    settings = get_settings()
    if not settings.enabled:
        return "muscle is paused (enabled=false). Re-enable it to read history."
    _prepare(settings)
    limit = _int(data.get("limit"), 8, 1, 40)
    try:
        return render.recent(db.recent(limit))
    except Exception as exc:  # pragma: no cover
        return f"Error: could not read recent commands ({exc})."


def shell_habits(args: dict | None = None, **kwargs: Any) -> str:
    data = args or {}
    settings = get_settings()
    if not settings.enabled:
        return "muscle is paused (enabled=false). Re-enable it to read history."
    _prepare(settings)
    topic = str(data.get("topic") or "").strip()
    limit = _int(data.get("limit"), 10, 1, 30)
    try:
        stats = db.stats()
        return render.habits(
            topic=topic,
            commands=db.top_norms(topic, limit),
            programs=db.top_programs(10),
            aliases=db.definitions("alias", 20),
            functions=db.definitions("function", 30),
            total=stats["total"],
        )
    except Exception as exc:  # pragma: no cover
        return f"Error: could not summarise the index ({exc})."


def shell_index(args: dict | None = None, **kwargs: Any) -> str:
    data = args or {}
    settings = get_settings()
    if not settings.enabled:
        return "muscle is paused (enabled=false). Run /muscle resume first."
    rebuild = bool(data.get("rebuild"))
    try:
        report = ingest.scan(settings, rebuild=rebuild)
    except Exception as exc:  # pragma: no cover
        return f"Error: indexing failed ({exc})."
    lines = [
        f"{'rebuilt' if rebuild else 'indexed'}: {report.inserted:,} new records from "
        f"{report.files} history file{'s' if report.files != 1 else ''} "
        f"({report.parsed:,} parsed, {report.skipped:,} skipped, "
        f"{report.aliases} aliases, {report.functions} functions) in {report.seconds:.2f}s.",
        f"index: {db.stats()['total']:,} records.",
    ]
    if report.errors:
        lines.append("could not read: " + "; ".join(report.errors[:3]))
    return "\n".join(lines)
