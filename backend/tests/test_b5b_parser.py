"""Phase B5b — HTML parser + entity extraction.

These tests pin the PLAN.md:282–284 contract:

* ``body_text`` is raw text from BeautifulSoup; ``body_text_clean`` is
  NULL-stripped, C0-stripped (except \\t\\n\\r), NFC-normalised, capped at
  512 KB UTF-8 bytes.
* Entity values get the same cleaning plus a BiDi-override strip, capped
  at 2 KB UTF-8 bytes.
* Entity extraction runs on a BiDi-stripped corpus so hidden addresses
  surface. The stored ``body_text_clean`` itself still contains the BiDi
  marks (an analyst should see what the page rendered).
* Content-Type allowlist exposes a helper for the runtime gate.
"""
from __future__ import annotations

import unicodedata

import pytest

from backend.crawler.parser import (
    PARSEABLE_CONTENT_TYPES,
    ParseResult,
    extract_entities,
    is_parseable_content_type,
    normalize_body_clean,
    normalize_entity_value,
    parse_html,
)


# A real v3 onion (56-char base32). Used across several tests.
ONION_V3 = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion"


# ---------------------------------------------------------------------------
# normalize_body_clean — PLAN.md:283
# ---------------------------------------------------------------------------


def test_normalize_body_clean_strips_null_and_c0_keeps_tab_lf_cr():
    raw = "a\x00b\x01c\x08d\te\nf\rg\x1fh"
    out = normalize_body_clean(raw)
    # NULL + C0 (\x01, \x08, \x1f) dropped; TAB/LF/CR retained.
    assert out == "abcd\te\nf\rgh"


def test_normalize_body_clean_applies_nfc():
    # e + combining acute → single precomposed é.
    raw = "café"
    out = normalize_body_clean(raw)
    assert out == "café"
    assert unicodedata.is_normalized("NFC", out)


def test_normalize_body_clean_caps_at_512kb_utf8():
    # 600 KB of ASCII (1 byte/char) should clamp exactly to 512 KB.
    raw = "x" * (600 * 1024)
    out = normalize_body_clean(raw)
    assert len(out.encode("utf-8")) == 512 * 1024


def test_normalize_body_clean_truncation_handles_multibyte_boundary():
    """A cut at a multi-byte boundary discards the partial code point."""
    # 4-byte emoji repeated past the cap. 130000 * 4 ≈ 520 KB > 512 KB.
    raw = "🦊" * 130_000
    out = normalize_body_clean(raw)
    encoded = out.encode("utf-8")
    assert len(encoded) <= 512 * 1024
    # No U+FFFD replacement chars introduced at the cut.
    assert "�" not in out


def test_normalize_body_clean_preserves_bidi_marks():
    """PLAN.md:283 doesn't strip BiDi from the body — only entity values do."""
    raw = "before‮inside‬after"
    out = normalize_body_clean(raw)
    assert "‮" in out
    assert "‬" in out


# ---------------------------------------------------------------------------
# normalize_entity_value — PLAN.md:284
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bidi", ["‪", "‫", "‬", "‭", "‮",
                                  "⁦", "⁧", "⁨", "⁩", "‏"])
def test_normalize_entity_value_strips_each_bidi_codepoint(bidi):
    value = f"prefix{bidi}suffix"
    assert normalize_entity_value(value) == "prefixsuffix"


def test_normalize_entity_value_caps_at_2kb_utf8():
    out = normalize_entity_value("a" * 5_000)
    assert len(out.encode("utf-8")) == 2 * 1024


def test_normalize_entity_value_is_idempotent_on_clean_input():
    clean = "alice@example.com"
    assert normalize_entity_value(clean) == clean
    assert normalize_entity_value(normalize_entity_value(clean)) == clean


# ---------------------------------------------------------------------------
# extract_entities — PLAN.md:282
# ---------------------------------------------------------------------------


def test_extract_entities_emails_dedupe():
    text = "ping alice@example.com and bob@example.com and again alice@example.com"
    ents = extract_entities(text)
    assert ("email", "alice@example.com") in ents
    assert ("email", "bob@example.com") in ents
    # Dedupe by (type, value).
    assert sum(1 for t, v in ents if (t, v) == ("email", "alice@example.com")) == 1


def test_extract_entities_btc_legacy_and_bech32():
    text = (
        "legacy 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa "
        "bech32 bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
    )
    ents = extract_entities(text)
    assert ("btc", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa") in ents
    assert ("btc", "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq") in ents


def test_extract_entities_xmr_address():
    addr = "4" + "A" + ("9" * 93)  # 95 chars; second char in [0-9AB]; rest from base58.
    text = f"send to {addr} thanks"
    ents = extract_entities(text)
    assert ("xmr", addr) in ents


def test_extract_entities_pgp_fingerprint_uppercase_only():
    fp_upper = "DEADBEEF" * 5  # 40 uppercase hex chars
    fp_lower = "deadbeef" * 5
    ents = extract_entities(f"upper {fp_upper} lower {fp_lower}")
    pgp_values = {v for t, v in ents if t == "pgp"}
    assert fp_upper in pgp_values
    assert fp_lower not in pgp_values  # lowercase is not a PGP fingerprint


def test_extract_entities_onion_v2_and_v3():
    v2 = "abcdefghij234567.onion"
    text = f"see {ONION_V3} and the old {v2} too"
    ents = extract_entities(text)
    onions = {v for t, v in ents if t == "onion"}
    assert ONION_V3 in onions
    assert v2 in onions


def test_extract_entities_i2p_name_and_b32():
    b32 = ("a" * 52) + ".b32.i2p"
    name = "forum.i2p"
    text = f"visit {name} or the {b32} mirror"
    ents = extract_entities(text)
    i2ps = {v for t, v in ents if t == "i2p"}
    assert name in i2ps
    assert b32 in i2ps
    # The .i2p suffix is distinct from .onion — no cross-contamination.
    assert not any(t == "onion" for t, _ in ents)


def test_extract_entities_handle_requires_two_occurrences():
    text = "follow @alice for updates, see @alice's stream. also @once_only"
    ents = extract_entities(text)
    handles = {v for t, v in ents if t == "handle"}
    assert "@alice" in handles
    assert "@once_only" not in handles


def test_extract_entities_blob_hex_dump():
    blob = "deadbeef" * 16  # 128 hex chars, even length
    text = f"dump:\n{blob}\nend"
    ents = extract_entities(text)
    blobs = {v for t, v in ents if t == "blob"}
    assert blob[:80] in blobs


def test_extract_entities_blob_excludes_onion_id_overlap():
    """Onion IDs satisfy the base64 alphabet — must not be double-counted."""
    text = f"site {ONION_V3} ok"
    ents = extract_entities(text)
    assert ("onion", ONION_V3) in ents
    # The 56-char ID prefix would otherwise look like a base64 blob.
    assert not any(t == "blob" for t, _ in ents)


def test_extract_entities_finds_address_obscured_by_bidi_override():
    """BiDi-stripped corpus is what the regex sees."""
    address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    # Insert U+202E mid-address; a naïve scanner would miss it.
    hidden = address[:5] + "‮" + address[5:]
    text = f"pay {hidden} now"
    ents = extract_entities(text)
    assert ("btc", address) in ents


# ---------------------------------------------------------------------------
# parse_html — soup-level integration
# ---------------------------------------------------------------------------


def test_parse_html_extracts_title_and_drops_script_style():
    html = (
        b"<html><head><title>Hi</title></head>"
        b"<body><script>alert('x')</script>"
        b"<style>body{color:red}</style>"
        b"<p>email me at boss@corp.io</p></body></html>"
    )
    result = parse_html(html)
    assert result.title == "Hi"
    # Scripts and styles must not pollute body_text.
    assert "alert" not in result.body_text
    assert "color:red" not in result.body_text
    # Email survives.
    assert ("email", "boss@corp.io") in result.entities


def test_parse_html_returns_none_title_when_missing_or_empty():
    assert parse_html(b"<html><body>no title</body></html>").title is None
    assert parse_html(b"<html><head><title>   </title></head></html>").title is None


def test_parse_html_resolves_relative_onion_links():
    base = f"http://{ONION_V3}/"
    html = (
        f'<a href="/path?q=1">A</a>'
        f'<a href="http://{ONION_V3}/abs">B</a>'
        '<a href="https://example.com/">C</a>'  # clearnet — dropped
        '<a href="javascript:bad()">D</a>'      # scheme — dropped
        '<a href="#frag">E</a>'                 # fragment — dropped
    ).encode("utf-8")
    result = parse_html(html, base_url=base)
    urls = [u for u, _ in result.links]
    assert f"http://{ONION_V3}/path?q=1" in urls
    assert f"http://{ONION_V3}/abs" in urls
    assert all(".onion" in u for u in urls)
    assert len(urls) == 2


def test_parse_html_resolves_i2p_links():
    base = "http://forum.i2p/"
    b32 = ("b" * 52) + ".b32.i2p"
    html = (
        '<a href="/path?q=1">A</a>'           # relative → forum.i2p
        f'<a href="http://{b32}/abs">B</a>'   # absolute b32 eepsite
        '<a href="https://example.com/">C</a>'  # clearnet — dropped
    ).encode("utf-8")
    result = parse_html(html, base_url=base)
    urls = [u for u, _ in result.links]
    assert "http://forum.i2p/path?q=1" in urls
    assert f"http://{b32}/abs" in urls
    assert all(".i2p" in u for u in urls)
    assert len(urls) == 2


def test_parse_html_dedupes_links_and_captures_anchor_text():
    base = f"http://{ONION_V3}/"
    html = (
        f'<a href="/x">first</a>'
        f'<a href="/x">duplicate</a>'  # collapses
        f'<a href="/y">  Second  </a>'
    ).encode("utf-8")
    result = parse_html(html, base_url=base)
    by_url = dict(result.links)
    assert by_url[f"http://{ONION_V3}/x"] == "first"
    assert by_url[f"http://{ONION_V3}/y"] == "Second"
    assert len(result.links) == 2


def test_parse_html_strips_link_fragments_before_dedupe():
    base = f"http://{ONION_V3}/"
    html = (
        f'<a href="/page#one">a</a>'
        f'<a href="/page#two">b</a>'
    ).encode("utf-8")
    result = parse_html(html, base_url=base)
    # Both anchors resolve to the same fragmentless URL → one link.
    assert len(result.links) == 1
    assert result.links[0][0] == f"http://{ONION_V3}/page"


def test_parse_html_drops_v2_onion_links():
    """Only v3 onions are crawlable (security/net rejects v2)."""
    base = f"http://{ONION_V3}/"
    html = b'<a href="http://abcdefghij234567.onion/">v2</a>'
    result = parse_html(html, base_url=base)
    assert result.links == []


def test_parse_html_body_text_clean_passes_through_normalization():
    html = b"<p>cafe\xcc\x81 stuff\x00here</p>"  # cafe + combining acute + NUL
    result = parse_html(html)
    assert "\x00" not in result.body_text_clean
    assert "café" in result.body_text_clean
    assert unicodedata.is_normalized("NFC", result.body_text_clean)


def test_parse_html_returns_dataclass():
    result = parse_html(b"<p>hi</p>")
    assert isinstance(result, ParseResult)
    assert isinstance(result.entities, list)
    assert isinstance(result.links, list)


# ---------------------------------------------------------------------------
# Content-Type gate — PLAN.md:287
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header",
    [
        "text/html",
        "text/html; charset=utf-8",
        "TEXT/HTML",
        "application/xhtml+xml",
        " application/xhtml+xml ; charset=utf-8 ",
    ],
)
def test_is_parseable_content_type_accepts_allowlist(header):
    assert is_parseable_content_type(header)


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "application/json",
        "application/octet-stream",
        "image/png",
        "text/plain",
    ],
)
def test_is_parseable_content_type_rejects_anything_else(header):
    assert not is_parseable_content_type(header)


def test_parseable_content_types_constant_matches_helper():
    for media_type in PARSEABLE_CONTENT_TYPES:
        assert is_parseable_content_type(media_type)
