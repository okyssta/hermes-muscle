from __future__ import annotations

import time

from muscle import db
from muscle.parsing import Entry


def _entries():
    now = 1_760_000_000
    return [
        Entry("git status", now, "bash", "/tmp/hist", "~/code/blog"),
        Entry("git status", now + 10, "bash", "/tmp/hist", "~/code/blog"),
        Entry("ffmpeg -i a.mp4 -vn a.opus", now + 20, "bash", "/tmp/hist", "~/media"),
        Entry("systemctl --user restart blog", now + 30, "bash", "/tmp/hist", "~/code/blog"),
    ]


def test_add_and_dedupe(home):
    assert db.add_entries(_entries()) == 4
    assert db.add_entries(_entries()) == 0
    assert db.stats()["total"] == 4


def test_search_returns_matching_rows(home):
    db.add_entries(_entries())
    rows = db.search("ffmpeg opus")
    assert rows and "ffmpeg" in rows[0]["command"]
    assert db.uses(rows[0]["norm"]) == 1


def test_search_uses_frequency(home):
    db.add_entries(_entries())
    rows = db.search("git")
    assert rows and db.uses(rows[0]["norm"]) == 2


def test_fts_query_is_sanitized(home):
    db.add_entries(_entries())
    assert db.fts_query('git " OR 1=1') == '"git"* OR "1"* OR "1"*'
    assert db.fts_query("AND OR NEAR") == ""
    assert db.search("AND OR NEAR") == []
    assert db.search('git " OR 1=1')  # must not raise, must still find git


def test_time_bounds(home):
    db.add_entries(_entries())
    rows = db.search("git", since=1_760_000_005)
    assert rows and all((row["ts"] or 0) >= 1_760_000_005 for row in rows)
    rows = db.search("git", until=1_760_000_005)
    assert rows and all((row["ts"] or 0) <= 1_760_000_005 for row in rows)


def test_neighbours_are_ordered(home):
    db.add_entries(_entries())
    target = db.search("ffmpeg")[0]
    before, after = db.neighbours(target, span=2)
    assert before and before[-1]["ts"] <= target["ts"]
    assert after and after[0]["ts"] >= target["ts"]


def test_recent_and_definitions(home):
    db.add_entries(_entries())
    db.add_entries([Entry(command="git status --short", kind="alias", name="gs")])
    assert db.recent(2)[0]["ts"] is not None
    aliases = db.definitions("alias")
    assert aliases and aliases[0]["name"] == "gs"


def test_prune_keeps_newest(home):
    entries = [Entry(f"echo {index}", 1_760_000_000 + index, "bash", "/tmp/hist") for index in range(30)]
    db.add_entries(entries, max_commands=10)
    assert db.stats()["total"] == 10
    assert db.recent(1)[0]["command"] == "echo 29"


def test_forget_removes_everything_but_keeps_database(home):
    db.add_entries(_entries())
    assert db.forget() == 4
    assert db.stats()["total"] == 0
    assert db.db_path().exists()
    assert db.search("git") == []


def test_stats_reports_sources_and_chars(home):
    db.add_entries(_entries())
    stats = db.stats()
    assert stats["commands"] == 4
    assert stats["chars"] > 0
    assert stats["oldest"] == 1_760_000_000
    assert stats["bytes"] > 0


def test_search_empty_index_does_not_raise(home):
    assert db.search("anything") == []
    assert db.stats()["total"] == 0
