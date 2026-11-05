"""Parsers for the three shell history formats people actually have.

Nothing here executes a command or writes to the history files. The parsers are
deliberately tolerant: a history file is an append-only log written by a shell
over years, often with a truncated last line and at least one multi-line command
in it, so every malformed record is kept as text rather than dropped.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, replace
from pathlib import Path

from .redact import redact

_HOME = posixpath.normpath(Path.home().as_posix())

_BASH_STAMP = re.compile(r"^#(\d{9,})$")
_ZSH_RECORD = re.compile(r"^: (\d{9,}):(\d+);(.*)$", re.S)
_FISH_CMD = re.compile(r"^-\s+cmd:\s?(.*)$")
_FISH_WHEN = re.compile(r"^\s+when:\s*(\d{9,})\s*$")
_ALIAS = re.compile(
    r"""^\s*alias\s+(?P<name>[A-Za-z0-9_.:-]+)\s*=\s*(?P<q>['"]?)(?P<value>.*?)(?P=q)\s*$"""
)
_FISH_ALIAS = re.compile(r"""^\s*(?:alias|abbr\s+-a)\s+(?P<name>[A-Za-z0-9_.:-]+)\s+(?P<q>['"]?)(?P<value>.*?)(?P=q)\s*$""")
_FUNC_START = re.compile(r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_.:-]*)\s*(?:\(\))?\s*\{\s*$")
_FISH_FUNC = re.compile(r"^\s*function\s+([A-Za-z_][A-Za-z0-9_.:-]*)\s*$")


@dataclass
class Entry:
    command: str
    ts: float | None = None
    shell: str = ""
    source: str = ""
    cwd: str = ""
    kind: str = "command"          # command | alias | function
    name: str = ""

    def cleaned(self, *, do_redact: bool, min_chars: int) -> "Entry | None":
        text = self.command.strip("\x00").strip()
        if not text:
            return None
        if self.kind == "command" and (text.startswith("#") or len(text) < min_chars):
            return None
        if do_redact:
            text = redact(text)
        return replace(self, command=text)


def _balanced(text: str) -> bool:
    """Rough quote-balance check used only to decide whether a command continues."""
    single = double = False
    escaped = False
    for char in text:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not double:
            single = not single
        elif char == '"' and not single:
            double = not double
    return not single and not double


def _flush(buf: list[str], entries: list[Entry], *, ts: float | None, shell: str, source: str) -> None:
    if not buf:
        return
    command = "\n".join(buf).strip()
    if command:
        entries.append(Entry(command=command, ts=ts, shell=shell, source=source))
    buf.clear()


def _block_depth(text: str) -> int:
    """Rough shell-block depth, used only to keep multi-line commands together."""
    opens = len(re.findall(r"(?:^|[;\s])(?:do|then)\b|\{\s*$", text, re.M))
    closes = len(re.findall(r"(?:^|[;\s])(?:done|fi)\b|^\s*\}", text, re.M))
    return opens - closes


def _open_ended(text: str) -> bool:
    tail = text.rstrip()
    return tail.endswith(("\\", "|", "&&", "||", "then", "do", "{")) or _block_depth(text) > 0


def parse_bash(text: str, source: str = "") -> list[Entry]:
    entries: list[Entry] = []
    pending_ts: float | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal pending_ts
        _flush(buf, entries, ts=pending_ts, shell="bash", source=source)
        pending_ts = None

    for raw in text.splitlines():
        stamp = _BASH_STAMP.match(raw.strip())
        if stamp:
            flush()
            pending_ts = float(stamp.group(1))
            continue
        if not raw.strip():
            if buf:
                buf.append(raw)
            continue
        if not buf and raw.lstrip().startswith("#"):
            continue
        if buf:
            joined = "\n".join(buf)
            if _open_ended(joined) or not _balanced(joined):
                buf.append(raw)
                joined = "\n".join(buf)
                if not _open_ended(joined) and _balanced(joined):
                    flush()
                continue
            flush()
        buf.append(raw)
        if not _open_ended(raw) and _balanced(raw):
            flush()
    flush()
    return entries


def parse_zsh(text: str, source: str = "") -> list[Entry]:
    entries: list[Entry] = []
    current: Entry | None = None
    for raw in text.splitlines():
        record = _ZSH_RECORD.match(raw)
        if record:
            if current is not None:
                entries.append(current)
            current = Entry(
                command=record.group(3),
                ts=float(record.group(1)),
                shell="zsh",
                source=source,
            )
            continue
        if current is None:
            if raw.strip():
                current = Entry(command=raw, ts=None, shell="zsh", source=source)
            continue
        # A line that does not open a new `: ts:dur;` record belongs to the
        # previous command unless the file is a plain (non-extended) history.
        if raw.startswith(": ") or not raw.strip():
            continue
        if current.ts is None:
            # Plain zsh history: one command per line, backslash continuation.
            entries.append(current)
            current = Entry(command=raw, ts=None, shell="zsh", source=source)
        else:
            current.command = f"{current.command}\n{raw}"
    if current is not None:
        entries.append(current)
    return entries


def _fish_unescape(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\\\", "\\")


def parse_fish(text: str, source: str = "") -> list[Entry]:
    entries: list[Entry] = []
    command: str | None = None
    when: float | None = None
    for raw in text.splitlines():
        found = _FISH_CMD.match(raw)
        if found:
            if command is not None:
                entries.append(Entry(command=_fish_unescape(command), ts=when, shell="fish", source=source))
            command = found.group(1)
            when = None
            continue
        stamp = _FISH_WHEN.match(raw)
        if stamp and command is not None:
            when = float(stamp.group(1))
            continue
        if command is not None and raw.startswith("      ") and raw.strip():
            command = f"{command}\n{raw.strip()}"
    if command is not None:
        entries.append(Entry(command=_fish_unescape(command), ts=when, shell="fish", source=source))
    return entries


def parse_history(path: Path, text: str) -> list[Entry]:
    name = path.name.lower()
    if "zsh" in name:
        return parse_zsh(text, source=str(path))
    if "fish" in name:
        return parse_fish(text, source=str(path))
    return parse_bash(text, source=str(path))


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def extract_aliases(text: str, source: str, shell: str) -> list[Entry]:
    found: list[Entry] = []
    for raw in text.splitlines():
        match = _FISH_ALIAS.match(raw) if shell == "fish" else _ALIAS.match(raw)
        if not match:
            continue
        value = _unquote(match.group("value"))
        if not value:
            continue
        found.append(
            Entry(
                command=value,
                shell=shell,
                source=source,
                kind="alias",
                name=match.group("name"),
            )
        )
    return found


def extract_functions(text: str, source: str, shell: str) -> list[Entry]:
    lines = text.splitlines()
    found: list[Entry] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = _FISH_FUNC.match(line) if shell == "fish" else _FUNC_START.match(line)
        if not match:
            index += 1
            continue
        name = match.group(1)
        body: list[str] = []
        index += 1
        while index < len(lines):
            inner = lines[index]
            if shell == "fish" and inner.strip() == "end":
                break
            if shell != "fish" and inner.strip() == "}":
                break
            body.append(inner)
            index += 1
        if body:
            found.append(
                Entry(
                    command="\n".join(body).strip(),
                    shell=shell,
                    source=source,
                    kind="function",
                    name=name,
                )
            )
        index += 1
    return found


_CD = re.compile(r"^\s*(?:cd|pushd)\s+(.+?)\s*(?:&&.*)?$")


def _expand_home(path: str) -> str:
    if path == "~":
        return _HOME
    if path.startswith("~/"):
        return _HOME + path[1:]
    return path


def _shrink_home(path: str) -> str:
    if path == _HOME:
        return "~"
    if path.startswith(_HOME + "/"):
        return "~" + path[len(_HOME):]
    return path


def _virtual_cwd(current: str, target: str) -> str:
    target = _unquote(target.strip())
    if not target or "$" in target or "`" in target or "*" in target:
        return current
    if target in {"~", "$HOME"}:
        return "~"
    if target == "-":
        return current
    if target.startswith("~"):
        return _shrink_home(posixpath.normpath(_expand_home(target)))
    if target.startswith("/"):
        return posixpath.normpath(target)
    base = _expand_home(current)
    return _shrink_home(posixpath.normpath(posixpath.join(base, target)))


def infer_cwds(entries: list[Entry], start: str = "~") -> list[Entry]:
    """Attach a best-effort working directory by replaying ``cd`` commands.

    History files do not record cwd. Replaying the ``cd``/``pushd`` transitions
    is the only signal available, so the result is labelled "inferred" wherever
    it is shown. A wrong guess is worse than no guess: unresolvable targets
    leave the previous directory in place.
    """
    current = start
    out: list[Entry] = []
    for entry in entries:
        if entry.kind == "command":
            match = _CD.match(entry.command.splitlines()[0] if entry.command else "")
            if match and not entry.cwd:
                out.append(replace(entry, cwd=current))
                current = _virtual_cwd(current, match.group(1))
                continue
        out.append(replace(entry, cwd=entry.cwd or current))
    return out


def parse_rc(path: Path, text: str, *, aliases: bool = True, functions: bool = True) -> list[Entry]:
    name = path.name.lower()
    shell = "fish" if "fish" in name or path.suffix == ".fish" else ("zsh" if "zsh" in name else "bash")
    found: list[Entry] = []
    if aliases:
        found.extend(extract_aliases(text, str(path), shell))
    if functions:
        found.extend(extract_functions(text, str(path), shell))
    return found
