"""Tool schemas, written for a model that has never seen this plugin."""

from __future__ import annotations

SHELL_RECALL = {
    "name": "shell_recall",
    "description": (
        "Search the user's own shell history — the commands they have actually typed on this "
        "machine, indexed locally. Use this whenever the user refers to something they ran "
        "rather than something they can paste: 'what was that ffmpeg command?', 'how did I "
        "deploy the blog last time?', 'the curl I used for that API', 'what flag did I use'. "
        "Returns the exact commands with timestamps, the directory they ran in, and how often "
        "each was used. Prefer this over guessing flags or asking the user to retype a command."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Words from the command or what it did, e.g. 'ffmpeg audio', 'deploy blog', 'stripe curl'.",
            },
            "since": {
                "type": "string",
                "description": "Lower time bound: 'today', 'yesterday', '7d', '2h', '2026-11-01'. Empty means any time.",
            },
            "until": {"type": "string", "description": "Upper time bound, same forms. Usually empty."},
            "limit": {"type": "integer", "description": "How many matches (default 8, max 25)."},
            "include_definitions": {
                "type": "boolean",
                "description": "Also match aliases and shell functions the user defined. Default false.",
            },
        },
        "required": ["query"],
    },
}

SHELL_SHOW = {
    "name": "shell_show",
    "description": (
        "Show one command from the shell-history index in full, including newlines, the directory "
        "it ran in, how many times it was used, and the commands immediately before and after it. "
        "Use it after shell_recall when the exact text or the surrounding workflow matters."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "The numeric id shown as [#id] by shell_recall or shell_last."},
        },
        "required": ["id"],
    },
}

SHELL_LAST = {
    "name": "shell_last",
    "description": (
        "List the most recent commands in the user's shell history, newest first. Use it for "
        "'what did I just run?', 'what was I doing before this?', or to recover the command the "
        "user is referring to when they say 'that last one'. It reads history, not the live "
        "terminal, so the very last command may not be flushed yet."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "How many commands (default 8, max 40)."},
        },
        "required": [],
    },
}

SHELL_HABITS = {
    "name": "shell_habits",
    "description": (
        "Summarise how the user actually works in the shell: their most repeated commands, most "
        "used programs, aliases and shell functions. Use it before writing instructions for them "
        "('how do I usually...'), to match their conventions (uv vs pip, pnpm vs npm), or when a "
        "recall search found nothing and you need to see what is in the index."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Optional word to focus on, e.g. 'git', 'docker', 'ffmpeg'. Empty gives the overall picture."},
            "limit": {"type": "integer", "description": "How many repeated commands to show (default 10, max 30)."},
        },
        "required": [],
    },
}

SHELL_INDEX = {
    "name": "shell_index",
    "description": (
        "Index or refresh the user's shell history and rc files. Normally unnecessary: the index "
        "builds itself on first use and refreshes automatically. Use it when the user added "
        "history entries that are not visible yet, changed their aliases, or asks to rebuild."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "rebuild": {"type": "boolean", "description": "Drop the index and re-read every file. Default false (incremental)."},
        },
        "required": [],
    },
}

ALL = [SHELL_RECALL, SHELL_SHOW, SHELL_LAST, SHELL_HABITS, SHELL_INDEX]
