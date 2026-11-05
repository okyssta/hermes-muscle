"""SQLite/FTS5 index for shell history.

One row per distinct command record (deduplicated by a hash of shell, source,
timestamp and text), plus aliases and functions from the user's rc files. The
index lives under the active profile's ``plugin-data/muscle/`` and is the only
thing this plugin writes.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from .parsing import Entry

PLUGIN_ID = "muscle"
_LOCK = threading.RLock()
_CONN: sqlite3.Connection | None = None
_CONN_PATH: Path | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    command TEXT NOT NULL,
    norm    TEXT NOT NULL,
    ts      REAL,
    cwd     TEXT NOT NULL DEFAULT '',
    shell   TEXT NOT NULL DEFAULT '',
    source  TEXT NOT NULL DEFAULT '',
    kind    TEXT NOT NULL DEFAULT 'command',
    name    TEXT NOT NULL DEFAULT '',
    hash    TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_entries_ts ON entries(ts DESC);
CREATE INDEX IF NOT EXISTS idx_entries_norm ON entries(norm);
CREATE INDEX IF NOT EXISTS idx_entries_kind ON entries(kind);
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    command,
    name,
    content='entries',
    content_rowid='id',
    tokenize="unicode61 tokenchars '_-./'"
);
CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, command, name) VALUES (new.id, new.command, new.name);
END;
CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, command, name) VALUES ('delete', old.id, old.command, old.name);
END;
"""


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))


def db_path() -> Path:
    return hermes_home() / "plugin-data" / PLUGIN_ID / "muscle.db"


def _connect() -> sqlite3.Connection:
    global _CONN, _CONN_PATH
    path = db_path()
    with _LOCK:
        if _CONN is not None and _CONN_PATH == path:
            return _CONN
        close()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=5.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(_SCHEMA)
        conn.commit()
        _CONN, _CONN_PATH = conn, path
        return conn


def close() -> None:
    global _CONN, _CONN_PATH
    with _LOCK:
        if _CONN is not None:
            try:
                _CONN.close()
            except Exception:
                pass
        _CONN, _CONN_PATH = None, None


def normalize(command: str) -> str:
    return " ".join(str(command).replace("\n", " ").split())


def _digest(entry: Entry) -> str:
    payload = "\x00".join(
        [
            entry.kind,
            entry.shell,
            entry.source,
            "" if entry.ts is None else f"{entry.ts:.3f}",
            entry.command,
            entry.name,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()


def add_entries(entries: Iterable[Entry], *, max_commands: int = 50000) -> int:
    rows = []
    for entry in entries:
        rows.append(
            (
                entry.command,
                normalize(entry.command),
                entry.ts,
                entry.cwd,
                entry.shell,
                entry.source,
                entry.kind,
                entry.name,
                _digest(entry),
            )
        )
    if not rows:
        return 0
    conn = _connect()
    with _LOCK:
        cursor = conn.executemany(
            "INSERT OR IGNORE INTO entries(command, norm, ts, cwd, shell, source, kind, name, hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        inserted = max(0, cursor.rowcount)
        _prune(conn, max_commands)
        conn.commit()
    return int(inserted)


def _prune(conn: sqlite3.Connection, max_commands: int) -> None:
    total = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    if total <= max_commands:
        return
    conn.execute(
        "DELETE FROM entries WHERE id NOT IN "
        "(SELECT id FROM entries ORDER BY COALESCE(ts, 0) DESC, id DESC LIMIT ?)",
        (max_commands,),
    )


# ---------------------------------------------------------------- queries

_TOKEN = re.compile(r"[A-Za-z0-9_./+-]{1,64}")


def fts_query(query: str) -> str:
    """Turn a user's words into a safe FTS5 expression.

    Quoted prefix terms joined with OR: "how did I strip audio" should match a
    command containing ``audio`` even if ``did`` never appears, which is the whole
    point of asking in natural language. Operators are stripped rather than
    passed through, so a stray quote cannot turn into a syntax error.
    """
    tokens = []
    for token in _TOKEN.findall(str(query or "")):
        cleaned = token.strip(".-/+")
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in {"and", "or", "not", "near"}:
            continue
        tokens.append(cleaned)
        if len(tokens) >= 12:
            break
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"*' for token in tokens)


def search(
    query: str,
    *,
    limit: int = 8,
    since: float | None = None,
    until: float | None = None,
    kinds: tuple[str, ...] = ("command",),
) -> list[sqlite3.Row]:
    conn = _connect()
    expression = fts_query(query)
    if not expression:
        return []
    placeholders = ",".join("?" for _ in kinds)
    clauses = [f"e.kind IN ({placeholders})"]
    args: list[Any] = list(kinds)
    if since is not None:
        clauses.append("(e.ts IS NULL OR e.ts >= ?)")
        args.append(since)
    if until is not None:
        clauses.append("(e.ts IS NULL OR e.ts <= ?)")
        args.append(until)
    sql = (
        "SELECT e.*, bm25(entries_fts) AS score FROM entries_fts f JOIN entries e ON e.id = f.rowid "
        f"WHERE entries_fts MATCH ? AND {' AND '.join(clauses)} "
        "ORDER BY bm25(entries_fts) ASC, e.ts DESC, e.id DESC LIMIT ?"
    )
    try:
        rows = conn.execute(sql, [expression, *args, max(limit * 6, limit)]).fetchall()
        # bm25 alone over-rewards a single rare word. For a natural-language
        # query, a command that contains several of the words the user said is
        # the better answer, so rank by coverage first, then relevance.
        tokens = [token.strip('"*').lower() for token in expression.split(" OR ")]
        ranked = sorted(
            rows,
            key=lambda row: (
                -sum(1 for token in tokens if token and token in (row["command"] + " " + row["name"]).lower()),
                row["score"],
                -(row["ts"] or 0),
            ),
        )
        # The same command typed on ten different days is one answer with a use
        # count, not ten rows. Keep the best-ranked instance of each command.
        seen: set[tuple[str, str, str]] = set()
        rows = []
        for row in ranked:
            key = (row["norm"], row["kind"], row["name"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
            if len(rows) >= limit:
                break
    except sqlite3.Error:
        # A malformed index or an FTS build without the tokenizer should still
        # answer something rather than raise into the agent loop.
        like = f"%{query.strip()}%"
        rows = conn.execute(
            f"SELECT e.*, 0.0 AS score FROM entries e WHERE e.command LIKE ? AND {' AND '.join(clauses)} "
            "ORDER BY e.ts DESC LIMIT ?",
            [like, *args, limit],
        ).fetchall()
    return list(rows)


def get(entry_id: int) -> sqlite3.Row | None:
    conn = _connect()
    return conn.execute("SELECT * FROM entries WHERE id = ?", (int(entry_id),)).fetchone()


def uses(norm: str) -> int:
    conn = _connect()
    return int(conn.execute("SELECT COUNT(*) FROM entries WHERE norm = ?", (norm,)).fetchone()[0])


def neighbours(row: sqlite3.Row, span: int = 3) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    conn = _connect()
    key = row["ts"] if row["ts"] is not None else 0
    before = conn.execute(
        "SELECT * FROM entries WHERE kind = 'command' AND id != ? AND COALESCE(ts,0) <= ? "
        "ORDER BY COALESCE(ts,0) DESC, id DESC LIMIT ?",
        (row["id"], key, span),
    ).fetchall()
    after = conn.execute(
        "SELECT * FROM entries WHERE kind = 'command' AND id != ? AND COALESCE(ts,0) >= ? "
        "ORDER BY COALESCE(ts,0) ASC, id ASC LIMIT ?",
        (row["id"], key, span),
    ).fetchall()
    return list(reversed(before)), list(after)


def recent(limit: int = 5, *, kind: str = "command") -> list[sqlite3.Row]:
    conn = _connect()
    return list(
        conn.execute(
            "SELECT * FROM entries WHERE kind = ? ORDER BY COALESCE(ts,0) DESC, id DESC LIMIT ?",
            (kind, limit),
        ).fetchall()
    )


def top_norms(topic: str = "", limit: int = 10) -> list[tuple[str, int, float | None]]:
    conn = _connect()
    if topic.strip():
        rows = search(topic, limit=500, kinds=("command",))
        norms = [row["norm"] for row in rows]
        if not norms:
            return []
        placeholders = ",".join("?" for _ in norms)
        data = conn.execute(
            f"SELECT norm, COUNT(*) c, MAX(ts) t FROM entries WHERE kind='command' AND norm IN ({placeholders}) "
            "GROUP BY norm ORDER BY c DESC LIMIT ?",
            [*norms, limit],
        ).fetchall()
    else:
        data = conn.execute(
            "SELECT norm, COUNT(*) c, MAX(ts) t FROM entries WHERE kind='command' "
            "GROUP BY norm ORDER BY c DESC, t DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [(row["norm"], int(row["c"]), row["t"]) for row in data]


_PROGRAM_KEYWORDS = {
    "for", "while", "until", "if", "then", "else", "elif", "do", "done",
    "case", "esac", "function", "fi", "{", "}", "time", "sudo", "env", "nohup",
    "command", "builtin", "exec", "xargs",
}


def top_programs(limit: int = 12) -> list[tuple[str, int]]:
    conn = _connect()
    rows = conn.execute(
        "SELECT norm FROM entries WHERE kind='command'"
    ).fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        parts = row["norm"].split()
        first = parts[0] if parts else ""
        if first in {"sudo", "env", "time", "nohup"} and len(parts) > 1:
            first = parts[1]
        if not first or first in _PROGRAM_KEYWORDS or first.startswith(("#", "export", "unset")):
            continue
        counts[first] = counts.get(first, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]


def definitions(kind: str, limit: int = 40) -> list[sqlite3.Row]:
    conn = _connect()
    return list(
        conn.execute(
            "SELECT * FROM entries WHERE kind = ? AND id IN "
            "(SELECT MAX(id) FROM entries WHERE kind = ? GROUP BY name) "
            "ORDER BY lower(name) LIMIT ?",
            (kind, kind, limit),
        ).fetchall()
    )


def stats() -> dict[str, Any]:
    conn = _connect()
    total = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    commands = conn.execute("SELECT COUNT(*) FROM entries WHERE kind='command'").fetchone()[0]
    defined = conn.execute("SELECT COUNT(*) FROM entries WHERE kind IN ('alias','function')").fetchone()[0]
    chars = conn.execute("SELECT COALESCE(SUM(LENGTH(command)),0) FROM entries").fetchone()[0]
    oldest = conn.execute("SELECT MIN(ts) FROM entries").fetchone()[0]
    newest = conn.execute("SELECT MAX(ts) FROM entries").fetchone()[0]
    sources = [row[0] for row in conn.execute("SELECT DISTINCT source FROM entries WHERE source != ''").fetchall()]
    path = db_path()
    return {
        "total": int(total),
        "commands": int(commands),
        "definitions": int(defined),
        "chars": int(chars),
        "oldest": oldest,
        "newest": newest,
        "sources": sources,
        "path": str(path),
        "bytes": path.stat().st_size if path.exists() else 0,
    }


def forget() -> int:
    conn = _connect()
    with _LOCK:
        total = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        conn.execute("DELETE FROM entries")
        conn.commit()
        conn.execute("VACUUM")
    return int(total)


def has_entries() -> bool:
    conn = _connect()
    return bool(conn.execute("SELECT 1 FROM entries LIMIT 1").fetchone())


def last_indexed() -> float:
    path = db_path()
    return path.stat().st_mtime if path.exists() else 0.0


def now() -> float:
    return time.time()
