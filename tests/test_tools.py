from __future__ import annotations

from muscle import db, ingest, tools
from muscle.parsing import Entry


def test_recall_finds_the_exact_command(configure, history):
    configure(history_files=[str(history)])
    text = tools.shell_recall({"query": "ffmpeg audio"})
    assert "ffmpeg -i talk.mp4 -vn -c:a libopus talk.opus" in text
    assert "2×" in text  # used twice
    assert "~/code/blog" in text


def test_recall_time_bounds_are_bounds(configure, history):
    configure(history_files=[str(history)])
    included = tools.shell_recall({"query": "ffmpeg", "since": "2000-01-01"})
    assert "ffmpeg" in included
    excluded = tools.shell_recall({"query": "ffmpeg", "until": "2000-01-01"})
    assert "No command" in excluded


def test_recall_redacts_secrets_at_storage_time(configure, history):
    configure(history_files=[str(history)])
    text = tools.shell_recall({"query": "OPENAI_API_KEY"})
    assert "[redacted" in text
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz012345" not in text
    stored = " ".join(row["command"] for row in db.recent(50))
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz012345" not in stored
    assert "eyJhbGciOiJIUzI1NiJ9" not in stored


def test_show_keeps_multiline_and_context(configure, history):
    configure(history_files=[str(history)])
    tools.shell_recall({"query": "ffmpeg"})
    db.add_entries(
        [
            Entry(
                "for f in *.log; do\n  wc -l \"$f\"\ndone",
                1_760_000_100,
                "bash",
                str(history),
                "~/code/blog",
            )
        ]
    )
    row = db.search("wc")[0]
    text = tools.shell_show({"id": row["id"]})
    assert "wc -l" in text
    assert "around it" in text


def test_show_rejects_bad_id(configure):
    configure()
    assert "numeric id" in tools.shell_show({"id": "nope"})
    assert "No command" in tools.shell_show({"id": 999})


def test_last_lists_newest_first(configure, history):
    configure(history_files=[str(history)])
    text = tools.shell_last({"limit": 3})
    headers = [line for line in text.splitlines() if line.startswith("[#")]
    commands = [line.strip() for line in text.splitlines() if line.startswith("    ")]
    assert "ffmpeg" in commands[0] and "blog-web" in commands[1]
    assert len(headers) == 3


def test_habits_summarises(configure, history, rc):
    configure(history_files=[str(history)], include_aliases=True)
    text = tools.shell_habits({"topic": "ffmpeg"})
    assert "most repeated commands" in text
    assert "ffmpeg" in text
    assert "git" in text.lower()


def test_index_is_idempotent(configure, history):
    configure(history_files=[str(history)])
    first = tools.shell_index({})
    assert "new records" in first
    second = tools.shell_index({})
    assert "0 new records" in second


def test_rebuild_starts_from_zero(configure, history):
    configure(history_files=[str(history)])
    tools.shell_index({})
    text = tools.shell_index({"rebuild": True})
    assert "rebuilt" in text
    assert db.stats()["total"] > 0


def test_empty_index_answers_helpfully(configure, tmp_path):
    empty = tmp_path / "empty_history"
    empty.write_text("", encoding="utf-8")
    configure(history_files=[str(empty)])
    text = tools.shell_recall({"query": "anything"})
    assert "No command" in text
    assert "shell_index" in text


def test_handlers_never_raise_on_bad_input(configure, history):
    configure(history_files=[str(history)])
    assert isinstance(tools.shell_recall({}), str)
    assert isinstance(tools.shell_recall({"query": "x", "limit": "not-a-number"}), str)
    assert isinstance(tools.shell_show({}), str)
    assert isinstance(tools.shell_last({"limit": None}), str)
    assert isinstance(tools.shell_habits({}), str)
    assert isinstance(tools.shell_index({}), str)


def test_paused_plugin_does_not_answer(configure, history):
    configure(history_files=[str(history)], enabled=False)
    assert "paused" in tools.shell_recall({"query": "ffmpeg"})
    assert "paused" in tools.shell_index({})
