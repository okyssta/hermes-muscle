"""Indexing: turn history and rc files into rows, incrementally.

A scan is idempotent. Every record is hashed; re-reading a history file that has
grown by ten lines inserts ten rows and skips the rest, and a full rebuild is
only needed after a config change.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import db
from .parsing import Entry, infer_cwds, parse_history, parse_rc
from .settings import Settings

_SCAN_LOCK = threading.Lock()
_LAST_SCAN = 0.0


@dataclass
class Report:
    files: int = 0
    parsed: int = 0
    inserted: int = 0
    skipped: int = 0
    aliases: int = 0
    functions: int = 0
    chars: int = 0
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


def collect(settings: Settings) -> tuple[list[Entry], Report]:
    report = Report()
    entries: list[Entry] = []
    for path in settings.files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            report.errors.append(f"{path}: {exc}")
            continue
        report.files += 1
        parsed = parse_history(path, text)
        report.parsed += len(parsed)
        entries.extend(parsed)

    entries = infer_cwds(entries)

    if settings.include_aliases or settings.include_functions:
        for path in settings.rc_files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                report.errors.append(f"{path}: {exc}")
                continue
            found = parse_rc(
                path,
                text,
                aliases=settings.include_aliases,
                functions=settings.include_functions,
            )
            for entry in found:
                if entry.kind == "alias":
                    report.aliases += 1
                elif entry.kind == "function":
                    report.functions += 1
            entries.extend(found)

    cleaned: list[Entry] = []
    for entry in entries:
        result = entry.cleaned(do_redact=settings.redact, min_chars=settings.min_command_chars)
        if result is None:
            report.skipped += 1
            continue
        cleaned.append(result)
    report.chars = sum(len(entry.command) for entry in cleaned)
    return cleaned, report


def scan(settings: Settings, *, rebuild: bool = False, max_commands: int | None = None) -> Report:
    started = time.perf_counter()
    if rebuild:
        db.forget()
    entries, report = collect(settings)
    report.inserted = db.add_entries(entries, max_commands=max_commands or settings.max_commands)
    report.seconds = time.perf_counter() - started
    return report


def ensure_indexed(settings: Settings, *, gap_seconds: float = 20.0) -> Report | None:
    """Index once on first use (and at most once per gap), in the caller's thread.

    A tool call that arrives before any indexing would otherwise answer "nothing
    found" on a machine with ten years of history — the worst first impression a
    memory plugin can make.
    """
    global _LAST_SCAN
    if not settings.enabled or not settings.auto_index:
        return None
    now = time.monotonic()
    with _SCAN_LOCK:
        if db.has_entries() and now - _LAST_SCAN < gap_seconds:
            return None
        _LAST_SCAN = now
        return scan(settings)


def background_index(settings: Settings) -> threading.Thread:
    thread = threading.Thread(target=lambda: _safe_scan(settings), name="muscle-index", daemon=True)
    thread.start()
    return thread


def _safe_scan(settings: Settings) -> None:
    try:
        scan(settings)
    except Exception:
        pass
