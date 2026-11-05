"""Text rendering.

The agent reads these strings, so they carry the facts needed to act: the exact
command, when it ran, the directory it ran in, how often it was used, and the id
to ask for more. No JSON, no decorative tables.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import db


def when(ts: Any) -> str:
    if ts in (None, ""):
        return "time unknown"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return "time unknown"


def one_line(command: str, width: int = 300) -> str:
    text = " ".join(str(command).split())
    if len(text) > width:
        text = text[: width - 1].rstrip() + "…"
    if "\n" in str(command):
        text += "  (multi-line; shell_show for the full command)"
    return text


def source_label(source: str, shell: str) -> str:
    if not source:
        return shell or "shell"
    return f"{shell or 'shell'} · {Path(source).name}"


def result_line(row: Any, *, show_uses: bool = True) -> str:
    uses = db.uses(row["norm"]) if show_uses else 1
    cwd = f" · {row['cwd']}" if row["cwd"] else ""
    count = f" · {uses}×" if uses > 1 else ""
    label = ""
    if row["kind"] == "alias":
        label = f"alias {row['name']} → "
    elif row["kind"] == "function":
        label = f"function {row['name']}() → "
    return (
        f"[#{row['id']}] {when(row['ts'])}{cwd}{count}\n"
        f"    {label}{one_line(row['command'])}"
    )


def results(query: str, rows: Sequence[Any], *, total: int, since: str = "", until: str = "") -> str:
    window = ""
    if since or until:
        window = f" ({since or 'beginning'} → {until or 'now'})"
    if not rows:
        return (
            f"No command in the index matches {query!r}{window}.\n"
            f"The index holds {total:,} records. Try fewer or more specific words, "
            "or shell_habits to see what is in there. If the history file was never "
            "indexed, run shell_index."
        )
    lines = [f"{len(rows)} match{'es' if len(rows) != 1 else ''} for {query!r}{window} (of {total:,} records):", ""]
    lines.extend(result_line(row) for row in rows)
    lines.append("")
    lines.append("Call shell_show(id) for the full command, its directory and what ran around it.")
    return "\n".join(lines)


def record(row: Any, before: Iterable[Any], after: Iterable[Any], uses: int) -> str:
    label = ""
    if row["kind"] == "alias":
        label = f"alias {row['name']} → "
    elif row["kind"] == "function":
        label = f"function {row['name']}()"
    lines = [
        f"[#{row['id']}] {when(row['ts'])} · {source_label(row['source'], row['shell'])}",
        f"directory: {row['cwd'] or 'unknown (inferred from cd commands, when possible)'}",
        f"used: {uses}×",
        "",
        f"{label}{row['command']}",
    ]
    if row["kind"] == "function":
        lines[-1] = f"function {row['name']}() {{\n{row['command']}\n}}"
    before_list = list(before)
    after_list = list(after)
    if before_list or after_list:
        lines.extend(["", "around it:"])
        for item in before_list:
            lines.append(f"  ← {when(item['ts'])}  {one_line(item['command'], 160)}")
        for item in after_list:
            lines.append(f"  → {when(item['ts'])}  {one_line(item['command'], 160)}")
    return "\n".join(lines)


def habits(
    *,
    topic: str,
    commands: Sequence[tuple[str, int, Any]],
    programs: Sequence[tuple[str, int]],
    aliases: Sequence[Any],
    functions: Sequence[Any],
    total: int,
) -> str:
    title = f"What the shell history says{(' about ' + repr(topic)) if topic else ''}"
    lines = [title, f"{total:,} records indexed.", ""]
    if commands:
        lines.append("most repeated commands:")
        for command, count, last in commands:
            lines.append(f"  {count:>3}×  {one_line(command, 180)}   (last {when(last)})")
    if programs:
        lines.append("")
        lines.append("most used programs: " + ", ".join(f"{name} ({count})" for name, count in programs))
    if aliases:
        lines.append("")
        lines.append("aliases you defined:")
        for row in aliases[:20]:
            lines.append(f"  {row['name']} → {one_line(row['command'], 140)}")
    if functions:
        lines.append("")
        lines.append("shell functions: " + ", ".join(row["name"] for row in functions[:30]))
    if not (commands or programs or aliases or functions):
        lines.append("Nothing indexed yet. Run shell_index.")
    return "\n".join(lines)


def recent(rows: Sequence[Any], *, label: str = "most recent commands") -> str:
    if not rows:
        return "The index is empty. Run shell_index."
    lines = [f"{label}:", ""]
    lines.extend(result_line(row) for row in rows)
    return "\n".join(lines)


def status(settings: Any) -> str:
    stats = db.stats()
    lines = [
        "muscle — the agent knows your shell",
        f"index: {stats['path']}",
        f"records: {stats['total']:,} ({stats['commands']:,} commands, {stats['definitions']:,} aliases/functions) · "
        f"{stats['chars']:,} chars · {stats['bytes'] / 1024:.0f} KiB",
        f"span: {when(stats['oldest'])} → {when(stats['newest'])}",
        f"sources: {len(stats['sources'])}",
        "",
        settings.describe(),
    ]
    if not stats["total"]:
        lines.append("")
        lines.append("Nothing indexed yet. Run /muscle index.")
    return "\n".join(lines)
