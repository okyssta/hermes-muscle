# Muscle

**Your agent knows your shell.**

Hermes can read any file you hand it, but it has no memory of the commands you
have actually typed: the ffmpeg invocation you worked out last month, the exact
`systemctl` sequence that restarts your blog, the `curl` with the odd header, the
directory where the tests pass. That knowledge is already on disk, in plain text,
in your shell history — unread.

`muscle` indexes the history and rc files your shells already write (bash, zsh and
fish; aliases and functions too) into a local SQLite/FTS5 index, and gives Hermes
five tools to search it. No capture daemon, no shell wrapper, no account, no
network. Secrets are redacted before anything is stored, and `/muscle forget`
deletes the index.

## What it adds

| Surface | Kind | What it does |
| --- | --- | --- |
| `shell_recall` | tool | Find a command by what it did: `"ffmpeg audio"`, `"deploy blog"`, `"stripe curl"` |
| `shell_show` | tool | One command in full — newlines preserved, the directory, the use count, and what ran immediately before and after |
| `shell_last` | tool | The most recent commands, newest first |
| `shell_habits` | tool | The shape of the user's shell: most repeated commands, most used programs, aliases, functions |
| `shell_index` | tool | Index or rebuild explicitly (normally automatic) |
| `/muscle` | command | `status`, `search`, `last`, `index`, `reindex`, `preview`, `forget`, `pause` |
| `muscle` | skill | When shell memory beats guessing or asking the user |

The agent-facing descriptions are written for a model that has never seen this
plugin: they say what the index is, when it beats guessing, and what the returned
id can be used for.

## Quickstart

```bash
# from the catalog, once published
hermes plugins install okyssta/hermes-muscle --enable

# or from a checkout
git clone https://github.com/okyssta/hermes-muscle ~/.hermes/plugins/muscle
hermes plugins enable muscle
```

That is the whole setup. On the next session the index builds itself from the
history files that already exist, and the first `shell_recall` is answered from
it.

## What it looks like (real demo output)

A seeded 39-command session, indexed in **0.02 s**:

```
$ python scripts/demo.py
1. Index the shell history that is already on disk
files=1 parsed=39 inserted=39 skipped=0 aliases=0 functions=0
index: 39 records, 1,190 chars, 4 KiB, 0.02s

2. 'What was that ffmpeg command I used to strip audio?'
4 matches for 'ffmpeg audio' (of 39 records):

[#34] 2026-08-11 17:45 · ~/work/blog · 3×
    ffmpeg -i talk.mp4 -vn -c:a libopus talk.opus
[#8] 2026-08-08 11:45 · ~/work/blog
    ffmpeg -i demo.mov -vn -c:a libopus demo.opus
```

```
3. 'How did I deploy the blog last time?'
6 matches for 'deploy blog restart' (of 39 records):

[#29] 2026-08-11 02:45 · ~/work/blog · 2×
    systemctl --user restart blog-web
[#21] 2026-08-10 02:45 · ~/work/api
    ssh blog 'systemctl --user restart blog-web'
```

`shell_show` returns the exact text, including multi-line commands, plus context:

```
[#28] 2026-08-10 23:45 · bash · .bash_history
directory: ~/work/blog
used: 1×

for f in *.log; do
  wc -l "$f"
done

around it:
  ← 2026-08-10 20:45  cd ~/work/blog
  → 2026-08-11 02:45  systemctl --user restart blog-web
```

Secrets are masked at the storage boundary, not at display time:

```
[#31] 2026-08-11 08:45 · ~/work/blog
    export OPENAI_API_KEY=[redacted]

sk-proj secret present in the index: False
bearer token present in the index: False
connection password present in the index: False
```

## Why this is not a skill

A skill can tell the model to run `history 50`. That returns the last fifty
commands in one terminal, not ten years of them; it has no ranking, no directory
attribution, no deduplication, no redaction, and no way to answer "which ffmpeg
did I use for the audio-only version". Muscle is a parser, an index, a ranker and
five tools. The skill shipped with it is only guidance for *when* to call them.

It is also different from memory plugins: memory stores what the agent and user
said; Muscle stores what the user *did*, in the shell, before Hermes existed.

## Privacy

- **Read-only on the history files.** Muscle never writes to, truncates or
  rewrites `~/.bash_history`, `~/.zsh_history` or fish history.
- **Redaction before storage.** API keys, bearer tokens, password/token/key
  assignments, credentials inside connection URLs (`postgres://user:pass@host`),
  `--password` flags and PEM private keys are masked as the row is inserted, not
  when it is displayed. Redaction is idempotent.
- **One local database.** It lives at
  `$HERMES_HOME/plugin-data/muscle/muscle.db`; nothing is sent anywhere.
- **Forget means forget.** `/muscle forget confirm` deletes every row, vacuums
  the database and leaves the history files untouched.
- **Preview before you commit.** `/muscle preview` shows the stats and the last
  few stored records (already redacted) and the rc files the index read.

A shell history is still sensitive: it reveals hosts, paths and habits even with
credentials masked. Muscle is local-only for that reason; point
`history_files` at a subset if you want to index less.

## How it works

**Formats.** Bash (`#<epoch>` timestamp lines, backslash and block continuations),
zsh extended history (`: <epoch>:<duration>;<command>`, multi-line records) and
fish (`- cmd:` / `when:`, YAML-escaped newlines). Plain one-command-per-line
histories work too.

**Directories.** History files do not record cwd. Muscle replays `cd` and `pushd`
transitions from the start of the file and attaches the resulting directory to
each command, resolving `~`, relative paths and `..`. A target containing a
variable or glob is not guessed — the previous directory stays. Treated as a hint
and labelled "inferred" in the docs, never as a fact.

**Ranking.** SQLite FTS5 with quoted prefix terms joined by `OR` (a natural-language
question should match a command that shares any of its words), then a coverage
pass: commands containing more of the user's words rank first, then BM25, then
recency. Identical commands collapse into one row with a use count.

**Aliases and functions.** `alias name=...`, fish `alias`/`abbr -a`, bash/zsh
`name() { ... }` and fish `function name ... end` are read from the usual rc
files (read-only). They are searchable with `include_definitions=true` and listed
by `shell_habits`.

**Idempotent indexing.** Every record is hashed (shell, source, timestamp, text,
name); re-reading a grown file inserts only the new lines. A cap
(`max_commands`, default 50,000) drops the oldest records first.

## Configuration

All keys are in `plugin.yaml` and settable with `hermes config set`:

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | true | Index and answer |
| `history_files` | [] | Extra files; empty means auto-detect (zsh, bash, fish, `$HISTFILE`) |
| `include_aliases` | true | Index aliases from rc files |
| `include_functions` | true | Index shell functions from rc files |
| `auto_index` | true | Build in the background at startup and refresh on first use |
| `max_commands` | 50000 | Oldest records beyond this are dropped |
| `redact` | true | Mask credential-shaped text before storage |
| `min_command_chars` | 4 | Ignore shorter entries |

## Limits, stated plainly

- **Not live.** Muscle reads history files, not the terminal. The very last
  command in an interactive shell may not be flushed yet; `shell_last` can lag by
  one prompt. It does not capture command output or exit codes.
- **cwd is inferred.** `cd` replay is the only signal available. A session that
  changed directories through a script or a subshell may be attributed to the
  wrong directory.
- **Multi-line is heuristic.** Backslash continuations, quotes and `do/then`
  blocks are joined; an unusual construction may be split into separate records.
  The text is never lost, only the grouping.
- **History is only as good as the shell's settings.** `HISTSIZE`/`HISTFILESIZE`
  caps, `HISTCONTROL=ignorespace` and erased history are outside the plugin's
  control.
- **Redaction is pattern-based.** It covers the common credential shapes listed
  above; a secret pasted in an unusual format can still reach the index. Local
  storage and `forget` are the backstop.

## Verify it yourself

```bash
# 41 tests, no network, no plugin host required
PYTHONPATH=. /root/peripheral/.venv/bin/python -m pytest -q

# the catalog gate
hermes plugins validate .

# end-to-end, against a seeded history in a throwaway HERMES_HOME
PYTHONPATH=. python scripts/demo.py
```

The demo is reproducible: `scripts/seed_demo_history.py` executes the commands it
records (failures expected) and spreads their timestamps over 90 days, so the
transcript above is what the code actually prints.

## Development

```
plugin.yaml          manifest (manifest_version 2, api_version 1)
__init__.py          register(): 5 tools, /muscle, bundled skill, background index
settings.py          config keys — one-for-one with config_schema
parsing.py           bash / zsh / fish parsers, alias + function extraction, cwd replay
redact.py            credential patterns applied at the storage boundary
db.py                SQLite + FTS5, ranking, dedupe, stats, forget
ingest.py            collect → clean → insert, incremental scan
tools.py             the five handlers (never raise)
commands.py          /muscle
render.py            the text the model reads
tests/               41 tests
scripts/             demo + demo-history seeder
```

MIT licensed.
