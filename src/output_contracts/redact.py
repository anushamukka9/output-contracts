"""PII and secret detection plus redaction.

All detection is regex and heuristic based, stdlib only. Detectors run
over plain text; scan_and_redact walks nested dicts/lists and redacts
every string value it finds, anywhere in the tree. Detection is
deterministic: the same input always produces the same output.
"""

from __future__ import annotations

import math
import re
from typing import Any

FULL = "full"
PARTIAL = "partial"
STYLES = (FULL, PARTIAL)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")

# JWT-shaped: header.payload.signature, base64url-ish segments.
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")

PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
    r".*?"
    r"-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
    re.DOTALL,
)

BEARER_RE = re.compile(r"\bBearer\s+([A-Za-z0-9\-._~+/]{8,}={0,2})")

PREFIXED_KEY_RE = re.compile(
    r"\b(?:sk-|ghp_|gho_|ghu_|ghr_|xoxb-|xoxp-|xoxa-|xoxo-)[A-Za-z0-9_\-]{8,}\b"
)

AKIA_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")

# ghp-style 40-char hex tokens.
HEX40_RE = re.compile(r"\b[0-9a-fA-F]{40}\b")

# SSN with obviously fake area/group/serial ranges excluded.
SSN_RE = re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

CARD_CANDIDATE_RE = re.compile(r"(?<!\d)(?:\d[ \-.']*){13,19}(?!\d)")

PHONE_INTL_RE = re.compile(r"(?<!\d)\+\d{1,3}[\s.\-]?(?:\(?\d+\)?[\s.\-]*){2,4}\d(?!\d)")
PHONE_US_RE = re.compile(r"(?<!\d)(?:\(\d{3}\)\s?|\d{3}[\s.\-])\d{3}[\s.\-]\d{4}(?!\d)")

# Long opaque strings, gated on entropy to keep prose safe.
GENERIC_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-+/=]{24,}\b")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    entropy = 0.0
    for count in counts.values():
        p = count / len(text)
        entropy -= p * math.log2(p)
    return entropy


def _regex_finder(pattern: re.Pattern[str]):
    def finder(text: str) -> list[tuple[int, int]]:
        return [(m.start(), m.end()) for m in pattern.finditer(text)]

    return finder


def _find_private_key(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in PRIVATE_KEY_RE.finditer(text)]


def _find_hex40(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in HEX40_RE.finditer(text)]


def _find_cards(text: str) -> list[tuple[int, int]]:
    spans = []
    for m in CARD_CANDIDATE_RE.finditer(text):
        raw = m.group(0).rstrip(" -.'")
        digits = re.sub(r"\D", "", raw)
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            spans.append((m.start(), m.start() + len(raw)))
    return spans


def _find_phones(text: str) -> list[tuple[int, int]]:
    spans = []
    for pattern in (PHONE_INTL_RE, PHONE_US_RE):
        for m in pattern.finditer(text):
            digits = re.sub(r"\D", "", m.group(0))
            if 7 <= len(digits) <= 15:
                spans.append((m.start(), m.end()))
    return spans


def _find_ipv4(text: str) -> list[tuple[int, int]]:
    spans = []
    for m in IPV4_RE.finditer(text):
        parts = m.group(0).split(".")
        if all(part.isdigit() and int(part) <= 255 for part in parts):
            spans.append((m.start(), m.end()))
    return spans


def _find_generic_tokens(text: str) -> list[tuple[int, int]]:
    spans = []
    for m in GENERIC_TOKEN_RE.finditer(text):
        token = m.group(0)
        has_letter = any(c.isalpha() for c in token)
        has_digit = any(c.isdigit() for c in token)
        if has_letter and has_digit and _shannon_entropy(token) >= 4.0:
            spans.append((m.start(), m.end()))
    return spans


# Ordered by priority: earlier detectors win on overlapping spans.
_DETECTORS: list[tuple[str, Any]] = [
    ("private_key", _find_private_key),
    ("jwt", _regex_finder(JWT_RE)),
    ("bearer_token", _regex_finder(BEARER_RE)),
    ("api_key", _regex_finder(PREFIXED_KEY_RE)),
    ("api_key", _regex_finder(AKIA_RE)),
    ("api_key", _find_hex40),
    ("email", _regex_finder(EMAIL_RE)),
    ("ssn", _regex_finder(SSN_RE)),
    ("credit_card", _find_cards),
    ("phone", _find_phones),
    ("ipv4", _find_ipv4),
    ("generic_token", _find_generic_tokens),
]


def find_matches(text: str) -> list[tuple[int, int, str]]:
    """Return non-overlapping (start, end, kind) matches in text.

    Earlier detectors in _DETECTORS win ties; longer spans win ties
    within one detector.
    """
    candidates: list[tuple[int, int, str, int]] = []
    for priority, (kind, finder) in enumerate(_DETECTORS):
        for start, end in finder(text):
            candidates.append((start, end, kind, priority))
    candidates.sort(key=lambda c: (c[0], c[3], -(c[1] - c[0])))
    kept: list[tuple[int, int, str]] = []
    for start, end, kind, _ in candidates:
        if all(end <= kstart or start >= kend for kstart, kend, _ in kept):
            kept.append((start, end, kind))
    kept.sort(key=lambda c: c[0])
    return kept


def redact_value(value: Any, kind: str, style: str = FULL) -> str:
    """Redact one string value. Full: [REDACTED:kind]. Partial: keep last 4."""
    if style not in STYLES:
        raise ValueError(f"unknown redaction style {style!r}; expected one of {list(STYLES)}")
    text = str(value)
    if style == FULL:
        return f"[REDACTED:{kind}]"
    if len(text) <= 4:
        return "****"
    return "*" * (len(text) - 4) + text[-4:]


def redact_text(text: str, style: str = FULL) -> tuple[str, list[tuple[int, int, str]]]:
    """Redact secrets in a single string. Returns (redacted, matches)."""
    matches = find_matches(text)
    if not matches:
        return text, []
    parts: list[str] = []
    cursor = 0
    for start, end, kind in matches:
        parts.append(text[cursor:start])
        parts.append(redact_value(text[start:end], kind, style))
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), matches


def scan_and_redact(data: Any, style: str = FULL) -> tuple[Any, list[dict[str, str]]]:
    """Redact detected secrets in every string value of a nested structure.

    Returns (redacted_data, redactions) where each redaction is a
    {"path": ..., "kind": ...} dict. Paths look like "user.email" and
    "items[2].token". Deterministic: same input, same output.
    """
    if style not in STYLES:
        raise ValueError(f"unknown redaction style {style!r}; expected one of {list(STYLES)}")
    redactions: list[dict[str, str]] = []
    redacted = _walk(data, "", style, redactions)
    return redacted, redactions


def _walk(node: Any, path: str, style: str, redactions: list[dict[str, str]]) -> Any:
    if isinstance(node, str):
        redacted, matches = redact_text(node, style)
        for _, _, kind in matches:
            redactions.append({"path": path, "kind": kind})
        return redacted
    if isinstance(node, dict):
        return {
            key: _walk(value, f"{path}.{key}" if path else str(key), style, redactions)
            for key, value in node.items()
        }
    if isinstance(node, (list, tuple)):
        walked = [_walk(value, f"{path}[{i}]", style, redactions) for i, value in enumerate(node)]
        return tuple(walked) if isinstance(node, tuple) else walked
    return node
