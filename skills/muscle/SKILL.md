---
name: muscle
description: "Search the user's own shell history before guessing a command."
version: 1.0.0
---

# Muscle — the user's shell, searchable

The user has typed thousands of commands on this machine. Most of the answers you
would otherwise guess — the right ffmpeg flags, the exact restart sequence, the
curl with the odd header — are already in their shell history, indexed by this
plugin.

## When to reach for it

- The user says **"that command"**, "the one I used before", "what was that…",
  "how did I do X last time", "the curl I used", "what flag did I use".
- You are about to **guess a CLI invocation** that involves a path, host, flag or
  service name the user has used before. Search first; a real command beats a
  plausible one.
- The user asks **"what did I just run?"** → `shell_last`.
- The user asks **"how do I usually …"**, or you need to match their conventions
  (uv vs pip, pnpm vs npm, their aliases) → `shell_habits`.

## How to use it well

1. `shell_recall` with the **words that describe the task**, not the whole
   command: `"ffmpeg audio"`, `"deploy blog"`, `"stripe webhook"`.
2. If several commands match, prefer the one with the higher use count and the
   more recent timestamp, and say which you picked.
3. Use `shell_show` when the exact text matters: it preserves newlines and shows
   the commands immediately before and after, which is often the real workflow.
4. Quote the command **exactly** as returned, including paths. If it contains
   `[redacted]`, do not invent a value — ask the user for the secret.
5. The index is built from history files, so the very last command in a live
   terminal may not be there yet. Say so if `shell_last` seems stale.

## What this is not

- It is not a live terminal. It cannot see running processes or output; it sees
  command lines.
- It does not store secrets: credentials are masked at insert time. Absence of a
  secret in a result is not permission to ask for it in chat.
- The directory shown is inferred by replaying `cd` commands, so treat it as a
  strong hint, not a guarantee.
