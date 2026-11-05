"""Settings for muscle — one source of truth for every config key.

Each field mirrors a ``config_schema`` entry in ``plugin.yaml`` one-for-one; a
test asserts the two key sets are identical. Values are coerced defensively so a
typo in ``config.yaml`` can never stop the plugin from answering.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLUGIN_ID = "muscle"

SCHEMA_KEYS = (
    "enabled",
    "history_files",
    "include_aliases",
    "include_functions",
    "auto_index",
    "max_commands",
    "redact",
    "min_command_chars",
)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
    return default


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _expand(raw: Any) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(raw).strip())))


def _split_paths(value: Any) -> list[Path]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part for part in value.replace(",", os.pathsep).split(os.pathsep) if part.strip()]
    elif isinstance(value, (list, tuple)):
        parts = [str(part) for part in value if str(part).strip()]
    else:
        return []
    seen: list[Path] = []
    for part in parts:
        path = _expand(part)
        if path not in seen:
            seen.append(path)
    return seen


# History files written by the shells people actually use. Ordered by how much
# history they usually hold; every one that exists is indexed.
_HISTORY_HINTS = (
    "~/.zsh_history",
    "~/.bash_history",
    "~/.local/share/fish/fish_history",
    "~/.histfile",
    "~/.sh_history",
    "~/.config/fish/fish_history",
)

# rc files that define aliases and functions. Read-only, never modified.
_RC_HINTS = (
    "~/.zshrc",
    "~/.bashrc",
    "~/.bash_aliases",
    "~/.profile",
    "~/.zshenv",
    "~/.config/fish/config.fish",
)


def default_history_files() -> list[Path]:
    """History files that exist on this machine, plus an explicit env override.

    ``HERMES_MUSCLE_HISTORY_FILES`` (os.pathsep-separated) exists so the demo and
    tests can point at a captured session without touching the user's own files.
    """
    override = os.environ.get("HERMES_MUSCLE_HISTORY_FILES")
    if override:
        return [path for path in _split_paths(override) if path.is_file()]
    found: list[Path] = []
    for hint in _HISTORY_HINTS:
        path = _expand(hint)
        if path.is_file() and path not in found:
            found.append(path)
    home = os.environ.get("HISTFILE")
    if home:
        path = _expand(home)
        if path.is_file() and path not in found:
            found.insert(0, path)
    return found


def default_rc_files() -> list[Path]:
    found: list[Path] = []
    for hint in _RC_HINTS:
        path = _expand(hint)
        if path.is_file() and path not in found:
            found.append(path)
    fish_functions = _expand("~/.config/fish/functions")
    if fish_functions.is_dir():
        for path in sorted(fish_functions.glob("*.fish"))[:200]:
            if path not in found:
                found.append(path)
    return found


@dataclass(frozen=True)
class Settings:
    enabled: bool = True
    history_files: tuple[Path, ...] = ()
    include_aliases: bool = True
    include_functions: bool = True
    auto_index: bool = True
    max_commands: int = 50000
    redact: bool = True
    min_command_chars: int = 4

    @property
    def files(self) -> tuple[Path, ...]:
        if self.history_files:
            return tuple(path for path in self.history_files if path.is_file())
        return tuple(default_history_files())

    @property
    def rc_files(self) -> tuple[Path, ...]:
        return tuple(default_rc_files()) if (self.include_aliases or self.include_functions) else ()

    def describe(self) -> str:
        files = self.files
        lines = [
            f"history files: {len(files)}",
            *[f"  {path}" for path in files[:8]],
        ]
        if len(files) > 8:
            lines.append(f"  … and {len(files) - 8} more")
        if not files:
            lines.append("  (none found — set history_files or HERMES_MUSCLE_HISTORY_FILES)")
        lines.append(
            f"aliases: {'on' if self.include_aliases else 'off'} · "
            f"functions: {'on' if self.include_functions else 'off'} · "
            f"auto-index: {'on' if self.auto_index else 'off'}"
        )
        lines.append(f"redact secrets: {'on' if self.redact else 'off'} · keep at most {self.max_commands:,} commands")
        return "\n".join(lines)

    @classmethod
    def from_ctx(cls, ctx: Any) -> "Settings":
        get = getattr(ctx, "get_config", None)
        if not callable(get):
            get = lambda _key, default=None: default  # noqa: E731 - older hosts
        return cls(
            enabled=_bool(get("enabled", True), True),
            history_files=tuple(_split_paths(get("history_files", []))),
            include_aliases=_bool(get("include_aliases", True), True),
            include_functions=_bool(get("include_functions", True), True),
            auto_index=_bool(get("auto_index", True), True),
            max_commands=_int(get("max_commands", 50000), 50000, 100, 500000),
            redact=_bool(get("redact", True), True),
            min_command_chars=_int(get("min_command_chars", 4), 4, 1, 40),
        )
