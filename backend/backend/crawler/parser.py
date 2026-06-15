"""HTML parser + entity extraction.

PLAN.md:282 — ``crawler/parser.py``: HTML → ``body_text`` (raw) +
``body_text_clean`` (stripped) + entity extraction
(``email``, ``btc``, ``xmr``, ``pgp``, ``onion``, ``handle``, ``blob``),
all with ``source='crawl'`` at the DB layer.

This module is pure: it takes bytes/string in and returns a structured
``ParseResult``. The crawl runtime (B5c) owns the aiohttp + DB write paths;
keeping the parser side-effect-free means we can unit-test the cleaning /
extraction contract without spinning up a network or a SQLite handle.

Normalisation contract:

* ``body_text_clean`` (PLAN.md:283) — strip NULL bytes, strip C0 control
  chars (except ``\\t``/``\\n``/``\\r``), Unicode NFC, cap at 512 KB UTF-8
  bytes. BiDi marks are deliberately preserved here so the stored text
  matches what an analyst would see in the page.
* Entity values (PLAN.md:284) — *additionally* strip BiDi override chars
  (U+202A–202E, U+2066–2069, U+200F) so an attacker can't hide an address
  inside a directional run; cap each value at 2 KB UTF-8 bytes.

Entity extraction itself runs against a BiDi-stripped copy of
``body_text_clean`` — without that step the regex would never see a
contiguous address when a page intersperses U+202E inside one.
"""
from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup

from ..security.net import I2P_URL_RE, ONION_URL_RE


# --- Limits & gates --------------------------------------------------------

_BODY_CLEAN_CAP_BYTES = 512 * 1024
_ENTITY_VALUE_CAP_BYTES = 2 * 1024

# PLAN.md:287 — only these Content-Type prefixes are parsed; the runtime
# uses this set when deciding whether to call ``parse_html`` at all.
PARSEABLE_CONTENT_TYPES: tuple[str, ...] = (
    "text/html",
    "application/xhtml+xml",
)


def is_parseable_content_type(value: str | None) -> bool:
    """Return True if ``value`` (a Content-Type header) matches the allowlist.

    Compares only the media-type prefix — charset/boundary parameters are
    ignored. ``None`` and empty values fail closed.
    """
    if not value:
        return False
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type in PARSEABLE_CONTENT_TYPES


# --- Cleaning helpers ------------------------------------------------------

# C0 controls (U+0000–U+001F) except TAB / LF / CR.
_C0_STRIP_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
# BiDi override / isolate / embedding marks (PLAN.md:284) that have been
# observed obscuring crypto addresses and onion URLs in dump pages.
_BIDI_RE = re.compile("[‪-‮⁦-⁩‏]")


def _truncate_utf8(text: str, limit: int) -> str:
    """Truncate ``text`` so its UTF-8 encoding is ≤ ``limit`` bytes.

    Decoding with ``errors='ignore'`` discards a partial multi-byte
    sequence at the cut point rather than emitting U+FFFD.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="ignore")


def normalize_body_clean(text: str) -> str:
    """Apply the PLAN.md:283 ``body_text_clean`` contract."""
    text = text.replace("\x00", "")
    text = _C0_STRIP_RE.sub("", text)
    text = unicodedata.normalize("NFC", text)
    return _truncate_utf8(text, _BODY_CLEAN_CAP_BYTES)


def normalize_entity_value(value: str) -> str:
    """Apply the PLAN.md:284 entity-value contract.

    Idempotent: callers that hand in an already-clean value get back the
    same string (modulo the 2 KB cap).
    """
    value = value.replace("\x00", "")
    value = _C0_STRIP_RE.sub("", value)
    value = _BIDI_RE.sub("", value)
    value = unicodedata.normalize("NFC", value)
    return _truncate_utf8(value, _ENTITY_VALUE_CAP_BYTES)


# --- Entity patterns -------------------------------------------------------

_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-z]{2,}", re.IGNORECASE)
_BTC_LEGACY = re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b")
_BTC_BECH32 = re.compile(r"\bbc1[a-z0-9]{39,59}\b")
# Monero standard address: starts with 4, 95 chars total, base58 alphabet.
_XMR = re.compile(r"\b4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b")
# PGP fingerprint: 40 uppercase hex chars (SHA-1 length). Lower-case hex
# would collide with arbitrary hash output, so we stay strict.
_PGP = re.compile(r"\b[0-9A-F]{40}\b")
_ONION_V3 = re.compile(r"\b[a-z2-7]{56}\.onion\b")
_ONION_V2 = re.compile(r"\b[a-z2-7]{16}\.onion\b")
# I2P eepsite hostnames. One suffix-anchored pattern covers both the human-
# readable address-book form (``forum.i2p``) and the cryptographic 52-char
# base32 destination form (``<b32>.b32.i2p``).
_I2P = re.compile(r"\b(?:[a-z0-9-]+\.)+i2p\b")
_HANDLE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{3,32}(?!\w)")
_HEX_BLOCK = re.compile(r"\b[0-9a-fA-F]{64,}\b")
_B64_BLOCK = re.compile(
    r"(?:[A-Za-z0-9+/]{4}){8,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?"
)

# Single-pass patterns; handles + blobs need extra logic and live below.
_SIMPLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", _EMAIL),
    ("btc", _BTC_LEGACY),
    ("btc", _BTC_BECH32),
    ("xmr", _XMR),
    ("pgp", _PGP),
    ("onion", _ONION_V3),
    ("onion", _ONION_V2),
    ("i2p", _I2P),
)

# Blob detection works on a fixed-length prefix so a multi-MB hex dump
# doesn't blow up the entities table.
_BLOB_VALUE_TRUNCATE = 80
# Handles below this repeat count are dropped as incidental @-mentions.
_HANDLE_MIN_COUNT = 2


def _iter_blob_spans(text: str) -> Iterable[tuple[int, int, str]]:
    """Yield ``(start, end, value)`` for hex / base64 blob candidates.

    Hex blobs: even-length runs of ≥ 64 hex chars. Base64 blobs must
    actually decode under strict validation. Both encodings collapse into
    the single ``blob`` entity type — the schema does not distinguish them.
    The caller is responsible for overlap exclusion (so a 56-char onion ID
    isn't double-counted as base64).
    """
    for match in _HEX_BLOCK.finditer(text):
        candidate = match.group(0)
        if len(candidate) % 2:
            continue
        yield match.start(), match.end(), candidate[:_BLOB_VALUE_TRUNCATE]
    for match in _B64_BLOCK.finditer(text):
        candidate = match.group(0)
        try:
            base64.b64decode(candidate, validate=True)
        except (binascii.Error, ValueError):
            continue
        yield match.start(), match.end(), candidate[:_BLOB_VALUE_TRUNCATE]


def extract_entities(body_text_clean: str) -> list[tuple[str, str]]:
    """Return ``[(type, value), ...]`` from ``body_text_clean``.

    BiDi marks are stripped from the *search corpus* before running the
    regexes — otherwise an attacker can hide an onion URL inside a
    directional run. The stored ``body_text_clean`` (DB-side) keeps the
    BiDi marks so an analyst sees what the page actually rendered.

    Blob detection runs last and skips any span that overlaps an already-
    claimed match. Without that step, an onion ID (56 base32 chars) would
    also pass the base64 validator and surface twice.
    """
    corpus = _BIDI_RE.sub("", body_text_clean)

    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    claimed: list[tuple[int, int]] = []

    def _overlaps(start: int, end: int) -> bool:
        return any(start < c_end and c_start < end for c_start, c_end in claimed)

    def _add(etype: str, raw: str) -> None:
        value = normalize_entity_value(raw)
        if not value:
            return
        key = (etype, value)
        if key in seen:
            return
        seen.add(key)
        out.append(key)

    for etype, pattern in _SIMPLE_PATTERNS:
        for match in pattern.finditer(corpus):
            _add(etype, match.group(0))
            claimed.append((match.start(), match.end()))

    # Handles only survive the 2-occurrence filter.
    handle_counts: dict[str, int] = {}
    handle_spans: dict[str, list[tuple[int, int]]] = {}
    for match in _HANDLE.finditer(corpus):
        handle = match.group(0)
        handle_counts[handle] = handle_counts.get(handle, 0) + 1
        handle_spans.setdefault(handle, []).append((match.start(), match.end()))
    for handle, count in handle_counts.items():
        if count >= _HANDLE_MIN_COUNT:
            _add("handle", handle)
            claimed.extend(handle_spans[handle])

    for start, end, value in _iter_blob_spans(corpus):
        if _overlaps(start, end):
            continue
        _add("blob", value)

    return out


# --- HTML → ParseResult ----------------------------------------------------

# Tags whose text content should never reach ``body_text``. ``template`` is
# included because <template> bodies are inert in browsers and would
# otherwise inflate the corpus with framework boilerplate.
_SKIP_TAGS = ("script", "style", "noscript", "template")


@dataclass(frozen=True)
class ParseResult:
    """Output of :func:`parse_html`. Pure data — no DB side-effects.

    ``links`` is a list of ``(absolute_url, anchor_text)`` for every
    ``<a href>`` that resolves to a valid v3 ``.onion`` URL after the
    ``base_url`` is applied. The runtime persists these via the edges
    table (PLAN.md:289).
    """

    title: str | None
    body_text: str
    body_text_clean: str
    entities: list[tuple[str, str]]
    links: list[tuple[str, str]]


def _resolve_crawl_link(href: str, base_url: str | None) -> str | None:
    """Return the absolute crawlable URL for ``href`` or None if not crawlable.

    Drops fragments, javascript:/mailto: schemes, and anything that doesn't
    match the v3 ``.onion`` or ``.i2p`` URL contract. v2 onions are dropped on
    purpose: the security layer rejects them (Tor deprecated v2 in 2021).
    """
    if not href:
        return None
    candidate = href.strip()
    if not candidate or candidate.startswith(("#", "javascript:", "mailto:", "data:")):
        return None
    if base_url:
        try:
            candidate = urljoin(base_url, candidate)
        except ValueError:
            return None
    candidate, _ = urldefrag(candidate)
    candidate = candidate.lower()
    if not (ONION_URL_RE.match(candidate) or I2P_URL_RE.match(candidate)):
        return None
    return candidate


def parse_html(html: str | bytes, base_url: str | None = None) -> ParseResult:
    """Parse ``html`` into title, body text, entities, and onion links.

    ``html`` may be bytes (BeautifulSoup sniffs the encoding from
    ``<meta charset>`` / BOM) or a decoded string. ``base_url`` resolves
    relative ``<a href>``s; if omitted, only absolute onion links are
    returned.
    """
    soup = BeautifulSoup(html, "lxml")

    # Drop non-content elements before extracting text so script bodies
    # don't pollute either ``body_text`` or the entity corpus.
    for tag in soup(_SKIP_TAGS):
        tag.decompose()

    title_tag = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else ""
    title = title_text or None

    body_text = soup.get_text("\n", strip=False)
    body_text_clean = normalize_body_clean(body_text)
    entities = extract_entities(body_text_clean)

    links: list[tuple[str, str]] = []
    seen_links: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute = _resolve_crawl_link(anchor["href"], base_url)
        if absolute is None or absolute in seen_links:
            continue
        seen_links.add(absolute)
        anchor_text = anchor.get_text(" ", strip=True)
        links.append((absolute, anchor_text))

    return ParseResult(
        title=title,
        body_text=body_text,
        body_text_clean=body_text_clean,
        entities=entities,
        links=links,
    )


__all__ = [
    "PARSEABLE_CONTENT_TYPES",
    "ParseResult",
    "extract_entities",
    "is_parseable_content_type",
    "normalize_body_clean",
    "normalize_entity_value",
    "parse_html",
]
