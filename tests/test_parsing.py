from __future__ import annotations

import pytest

from muscle.parsing import (
    Entry,
    extract_aliases,
    extract_functions,
    infer_cwds,
    parse_bash,
    parse_fish,
    parse_zsh,
)


def test_bash_reads_timestamps_and_multiline():
    text = "\n".join(
        [
            "#1700000000",
            "git status",
            "#1700000100",
            "for f in *.log; do",
            "  wc -l \"$f\"",
            "done",
            "#1700000200",
            "echo 'a very",
            "long value'",
        ]
    )
    entries = parse_bash(text)
    assert entries[0].command == "git status"
    assert entries[0].ts == 1700000000
    assert "done" in entries[1].command
    assert entries[1].ts == 1700000100
    assert "long value" in entries[2].command


def test_bash_backslash_continuation_is_one_record():
    text = "#1700000000\ndocker run \\\n  --rm \\\n  alpine echo hi\n"
    entries = parse_bash(text)
    assert len(entries) == 1
    assert "--rm" in entries[0].command and "alpine" in entries[0].command


def test_bash_ignores_comments_and_blank_lines():
    entries = parse_bash("#1700000000\n\n# just a comment\nls -la\n")
    assert [entry.command for entry in entries] == ["ls -la"]


def test_zsh_extended_history():
    text = ": 1700000000:12;git status\n: 1700000100:0;ffmpeg -i a.mp4 -vn out.opus\n"
    entries = parse_zsh(text)
    assert len(entries) == 2
    assert entries[1].command.startswith("ffmpeg")
    assert entries[1].ts == 1700000100


def test_zsh_multiline_record_is_preserved():
    text = ": 1700000000:0;for f in *.log; do\n  wc -l $f\ndone\n"
    entries = parse_zsh(text)
    assert len(entries) == 1
    assert "wc -l" in entries[0].command


def test_plain_zsh_history_one_per_line():
    entries = parse_zsh("ls -la\npwd\n")
    assert [entry.command for entry in entries] == ["ls -la", "pwd"]


def test_fish_history():
    text = "- cmd: git status\n  when: 1700000000\n- cmd: echo 'a\\nb'\n  when: 1700000100\n"
    entries = parse_fish(text)
    assert entries[0].command == "git status"
    assert entries[1].command == "echo 'a\nb'"


def test_alias_extraction():
    text = "alias gs='git status --short'\nalias ll='ls -la'\nalias blog='cd ~/blog'\n"
    entries = extract_aliases(text, "/tmp/.zshrc", "zsh")
    names = {entry.name for entry in entries}
    assert {"gs", "ll", "blog"} <= names
    assert "git status --short" in [entry.command for entry in entries]


def test_function_extraction():
    text = "deploy() {\n  git push\n  ssh host restart\n}\nother() { echo hi; }\n"
    entries = extract_functions(text, "/tmp/.bashrc", "bash")
    names = [entry.name for entry in entries]
    assert "deploy" in names


def test_cwd_inference_follows_cd():
    entries = [
        Entry("cd ~/code/blog"),
        Entry("git status"),
        Entry("cd .."),
        Entry("ls"),
        Entry("cd /tmp"),
        Entry("pwd"),
    ]
    out = infer_cwds(entries)
    assert out[1].cwd == "~/code/blog"
    assert out[3].cwd == "~/code"
    assert out[5].cwd == "/tmp"


def test_cwd_inference_ignores_variables():
    entries = [Entry("cd $PROJECT"), Entry("make")]
    out = infer_cwds(entries)
    assert out[1].cwd == out[0].cwd


def test_cleaned_redacts_and_rejects_short_entries():
    secret = Entry("export TOKEN=sk-proj-abcdefghijklmnopqrstuvwxyz012345")
    cleaned = secret.cleaned(do_redact=True, min_chars=4)
    assert cleaned is not None
    assert "sk-proj" not in cleaned.command
    assert "[redacted" in cleaned.command

    short = Entry("ls")
    assert short.cleaned(do_redact=True, min_chars=4) is None
