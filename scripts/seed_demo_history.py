#!/usr/bin/env python3
"""Create a realistic demo shell history.

The commands below are actually executed (failures are fine and expected) so the
text in the history is what a real shell session would contain; their timestamps
are then spread over the last 90 days so the demo can show recency filtering.
This file exists only to make the demo reproducible — the plugin itself always
reads the user's real history.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

COMMANDS = [
    "cd ~/work/blog",
    "git status",
    "git pull --rebase",
    "uv run pytest -q",
    "systemctl --user restart blog-web",
    "journalctl --user -u blog-web -n 50 --no-pager",
    "ffmpeg -i talk.mp4 -vn -c:a libopus talk.opus",
    "ffmpeg -i demo.mov -vn -c:a libopus demo.opus",
    "ls -lh *.opus",
    "ffmpeg -i talk.mp4 -vn -c:a libopus talk.opus",
    "grep -n 'ERROR' app.log | tail -20",
    "tail -n 100 app.log",
    "curl -sS -o /dev/null -w '%{http_code}\\n' http://127.0.0.1:5050/health",
    "psql postgres://app:correcthorse@127.0.0.1:5432/app -c 'select count(*) from users'",
    "uv add httpx",
    "uv run pytest tests/test_auth.py -q",
    "cd ../api",
    "uv run pytest -q",
    "docker compose up -d",
    "docker compose logs --tail=100 api",
    "ssh blog 'systemctl --user restart blog-web'",
    "rsync -avz ./dist/ blog:/srv/blog/",
    "tar -czf backup.tar.gz dist",
    "git rebase -i HEAD~3",
    "git push origin main",
    "git log --oneline -10",
    "cd ~/work/blog",
    "for f in *.log; do\n  wc -l \"$f\"\ndone",
    "systemctl --user restart blog-web",
    "curl -sS -H 'Authorization: Bearer demo-token-not-real' http://127.0.0.1:5050/api/me",
    "export OPENAI_API_KEY=sk-proj-demo000000000000000000000000000000",
    "unset OPENAI_API_KEY",
    "git status",
    "ffmpeg -i talk.mp4 -vn -c:a libopus talk.opus",
    "systemctl --user status blog-web --no-pager",
    "cd ~/work/api",
    "uv run pytest -q",
    "git commit -am 'fix: retry stripe webhook on 429'",
    "git push origin main",
]


def _run(command: str, cwd: Path) -> None:
    try:
        subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            timeout=4,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except Exception:
        pass


def build(destination: Path) -> Path:
    work = Path(tempfile.mkdtemp(prefix="muscle-demo-work-"))
    for name in ("blog", "api"):
        (work / name).mkdir(parents=True, exist_ok=True)
    (work / "blog" / "talk.mp4").write_bytes(b"not a real video\n" * 64)
    (work / "blog" / "demo.mov").write_bytes(b"not a real video\n" * 64)
    (work / "blog" / "app.log").write_text(
        "INFO  boot\nERROR stripe webhook returned 429\nINFO  retry scheduled\n" * 20,
        encoding="utf-8",
    )
    for name in ("blog", "api"):
        subprocess.run(["git", "init", "-q"], cwd=str(work / name), check=False)

    home = Path(tempfile.mkdtemp(prefix="muscle-demo-home-"))
    lines: list[str] = []
    base = int(time.time()) - 90 * 86400
    step = 3 * 3600
    for index, command in enumerate(COMMANDS):
        # Execute with $HOME pointed at the demo home so `cd ~/work/...` is real.
        _run(command.replace("~/work", str(work)), work / "blog")
        lines.append(f"#{base + index * step}")
        lines.append(command)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo/.bash_history")
    path = build(target)
    print(f"wrote {path} ({len(COMMANDS)} commands, {path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
