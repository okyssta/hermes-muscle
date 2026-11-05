#!/usr/bin/env python3
"""Index a synthetic 20,000-command history and report the numbers.

Run from the repo root:

    PYTHONPATH=. /root/peripheral/.venv/bin/python scripts/benchmark.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO.parent))
sys.path.insert(0, "/root/.hermes/hermes-agent")

COMMANDS = [
    "git status",
    "git pull --rebase",
    "uv run pytest -q",
    "ffmpeg -i talk.mp4 -vn -c:a libopus talk.opus",
    "systemctl --user restart blog-web",
    "curl -sS http://127.0.0.1:5050/health",
    "grep -n ERROR app.log | tail -20",
    "docker compose logs --tail=100 api",
    "cd ~/work/blog",
    "cd ../api",
    "rsync -avz ./dist/ blog:/srv/blog/",
    "ssh blog 'systemctl --user restart blog-web'",
]


def main(count: int = 20000) -> int:
    home = Path(tempfile.mkdtemp(prefix="muscle-bench-home-"))
    os.environ["HERMES_HOME"] = str(home)
    hist = Path(tempfile.mkdtemp(prefix="muscle-bench-hist-")) / ".bash_history"

    base = 1_700_000_000
    lines: list[str] = []
    for index in range(count):
        lines.append(f"#{base + index * 60}")
        lines.append(f"{COMMANDS[index % len(COMMANDS)]} --run {index}")
    hist.write_text("\n".join(lines) + "\n", encoding="utf-8")

    from muscle import db, ingest
    from muscle.settings import Settings

    class Ctx:
        config = {
            "history_files": [str(hist)],
            "include_aliases": False,
            "include_functions": False,
            "auto_index": False,
        }

        def get_config(self, key, default=None):
            return self.config.get(key, default)

    db.close()
    started = time.perf_counter()
    report = ingest.scan(Settings.from_ctx(Ctx()))
    elapsed = time.perf_counter() - started
    stats = db.stats()
    print(f"seed: {hist.stat().st_size:,} bytes")
    print(f"parsed={report.parsed:,} inserted={report.inserted:,} skipped={report.skipped:,}")
    print(f"index: {stats['total']:,} records, {stats['chars']:,} chars, {stats['bytes'] / 1024 / 1024:.2f} MiB")
    print(f"indexed in {elapsed:.2f}s ({report.parsed / elapsed:,.0f} records/s)")

    started = time.perf_counter()
    again = ingest.scan(Settings.from_ctx(Ctx()))
    print(f"warm rescan: inserted={again.inserted} in {time.perf_counter() - started:.2f}s")

    started = time.perf_counter()
    rows = db.search("ffmpeg audio", limit=8)
    print(f"search: {len(rows)} rows in {(time.perf_counter() - started) * 1000:.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
