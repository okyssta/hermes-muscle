#!/usr/bin/env python3
"""End-to-end demo: a seeded history in, exact commands out.

Run from the repo root:

    PYTHONPATH=. /root/peripheral/.venv/bin/python scripts/demo.py

Everything is local and throwaway: a temporary HERMES_HOME, a seeded history, a
fresh SQLite index. The printed transcript is the same one quoted in the README.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO.parent))
sys.path.insert(0, str(REPO))
sys.path.insert(0, "/root/.hermes/hermes-agent")


def hr(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> int:
    home = Path(tempfile.mkdtemp(prefix="muscle-demo-hermes-"))
    os.environ["HERMES_HOME"] = str(home)
    history = REPO / "demo" / ".bash_history"
    if not history.exists():
        from scripts.seed_demo_history import build

        build(history)

    import muscle
    from muscle import db, ingest, render, tools
    from muscle.settings import Settings

    class Ctx:
        config = {
            "history_files": [str(history)],
            "include_aliases": True,
            "include_functions": True,
            "auto_index": True,
        }

        def get_config(self, key, default=None):
            return self.config.get(key, default)

    muscle._CTX = Ctx()
    muscle._CACHED = None
    db.close()

    hr("1. Index the shell history that is already on disk")
    started = time.perf_counter()
    report = ingest.scan(Settings.from_ctx(muscle._CTX))
    elapsed = time.perf_counter() - started
    stats = db.stats()
    print(
        f"files={report.files} parsed={report.parsed} inserted={report.inserted} "
        f"skipped={report.skipped} aliases={report.aliases} functions={report.functions}"
    )
    print(
        f"index: {stats['total']} records, {stats['chars']:,} chars, "
        f"{stats['bytes'] / 1024:.0f} KiB, {elapsed:.2f}s"
    )

    hr("2. 'What was that ffmpeg command I used to strip audio?'")
    print(tools.shell_recall({"query": "ffmpeg audio"}))

    hr("3. 'How did I deploy the blog last time?'")
    print(tools.shell_recall({"query": "deploy blog restart"}))

    hr("4. The exact text, plus what ran around it")
    rows = db.search("wc -l")
    if rows:
        print(tools.shell_show({"id": rows[0]["id"]}))

    hr("5. Habits: what this shell actually uses")
    print(tools.shell_habits({"topic": "ffmpeg"}))

    hr("6. The very last commands")
    print(tools.shell_last({"limit": 4}))

    hr("7. Secrets are masked before storage")
    print(tools.shell_recall({"query": "OPENAI_API_KEY"}))
    stored = " ".join(row["command"] for row in db.recent(100))
    print()
    print("sk-proj secret present in the index:", "sk-proj-demo" in stored)
    print("bearer token present in the index:", "demo-token-not-real" in stored)
    print("connection password present in the index:", "correcthorse" in stored)

    hr("8. Incremental re-index is free")
    again = ingest.scan(Settings.from_ctx(muscle._CTX))
    print(f"second scan: inserted={again.inserted} parsed={again.parsed} in {again.seconds:.2f}s")

    hr("9. Forget actually empties the index")
    removed = db.forget()
    print(f"removed={removed} remaining={db.stats()['total']}")
    print("history file untouched:", history.exists(), f"({history.stat().st_size} bytes)")

    print()
    print("demo complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
