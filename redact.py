"""Secret redaction applied before anything is written to the index.

Shell history is the single richest accidental-secret file on a developer
machine: ``export GITHUB_TOKEN=...``, ``curl -H 'Authorization: Bearer ...'``,
``psql postgres://user:pass@host/db``. The index is only useful if it is safe to
keep, so redaction happens at the storage boundary — before truncation, never
after it (a cut can slice a token past a pattern).
"""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Well-known key shapes. Kept narrow on purpose: a 12-character threshold
    # here would mask ordinary prose and paths.
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[redacted:key]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b"), "[redacted:key]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[redacted:github]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[redacted:github]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[redacted:aws]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"), "[redacted:google]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[redacted:slack]"),
    (re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"), "[redacted:hf]"),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}\b"), "[redacted:gitlab]"),
    (re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b"), "[redacted:npm]"),
    # Authorization headers and query-string tokens.
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}"), r"\1 [redacted]"),
    # key=value / key: value where the key looks like a credential.
    (
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:PASSWORD|PASSWD|PWD|TOKEN|SECRET|API[_-]?KEY|APIKEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|AUTH)[A-Z0-9_]*)"
            r"(\s*[=:]\s*)([\"']?)([^\s\"'|;&]{6,})"
        ),
        r"\1\2\3[redacted]",
    ),
    # postgres://user:password@host — the pattern list above misses it.
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^:/\s]+:)([^@\s]+)(@)"), r"\1[redacted]\3"),
    # --password foo / --token=foo forms.
    (
        re.compile(
            r"(?i)(--?(?:password|passwd|token|secret|api-key|apikey|auth-token)[= ]+)([\"']?)([^\s\"']{4,})"
        ),
        r"\1\2[redacted]",
    ),
    # PEM blocks: mask the body but keep the fact that a key was involved.
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.S,
        ),
        "[redacted:private-key]",
    ),
    # Long hex/base64 values assigned to a suspiciously credential-ish variable
    # are already covered above; this catches bare 40+ hex digests in URLs.
    (re.compile(r"(?i)\b([?&](?:access_token|token|key|sig|signature)=)([A-Za-z0-9%._-]{16,})"), r"\1[redacted]"),
)


def redact(text: str) -> str:
    """Return *text* with credential-shaped substrings masked.

    Deterministic and idempotent: applying it twice changes nothing, which
    matters because a command can be redacted on insert and again on display.
    """
    if not text:
        return text
    result = str(text)
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def looks_like_secret_file(path: str) -> bool:
    """Paths whose *contents* should never be indexed as a command line."""
    lowered = str(path).lower()
    return any(
        marker in lowered
        for marker in (
            "/.ssh/",
            "id_rsa",
            "id_ed25519",
            "/.aws/credentials",
            "/.docker/config.json",
            "/.kube/config",
            "/.gnupg/",
            "/.netrc",
            "/.pgpass",
        )
    )
