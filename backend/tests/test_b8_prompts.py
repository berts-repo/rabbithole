"""Phase B8 — prompt templates + output validators.

Targets PLAN.md:348 — multi-page synthesis delimiter, output validators
drop malformed responses (non-int Risk Score, non-enum Category, oversize
Domain Label).
"""
from __future__ import annotations

import pytest

from backend.prompts import (
    AUTO_ENQUEUE_TYPES,
    CATEGORY_LABELS,
    DOMAIN_LABEL_MAX,
    MULTI_PAGE_INPUT_CAP,
    OutputValidationError,
    PROMPTS,
    render,
    render_multi,
)


# --- single-page render ----------------------------------------------------


def test_every_type_has_a_spec_and_validator():
    expected_keys = {
        "Summary",
        "Risk Score",
        "Category",
        "Domain Label",
        "Entities (LLM)",
        "Q&A",
        "Cluster Q&A",
        "Cluster Summary",
        "Site Relationships",
        "Investigation Digest",
        "Seed Suggestions",
    }
    assert set(PROMPTS.keys()) == expected_keys
    for spec in PROMPTS.values():
        assert callable(spec.output_validator)
        assert "{page_content}" in spec.user_template


def test_render_handles_brace_chars_in_content():
    """``str.replace`` is used (not ``str.format``) so braces never break."""
    spec = PROMPTS["Summary"]
    page = "page with {curly} and {literal{braces}} content"
    system, user = render(spec, page)
    assert page in user
    assert system  # system prompt non-empty


def test_render_truncates_to_input_cap_bytes():
    spec = PROMPTS["Summary"]
    huge = "x" * (spec.input_cap_bytes * 2)
    _system, user = render(spec, huge)
    # The user prompt = template (a few hundred chars) + truncated content.
    # The content slice itself must be ≤ cap.
    assert len(user.encode("utf-8")) <= spec.input_cap_bytes + len(spec.user_template) * 4


def test_render_multi_rejects_single_page_spec():
    with pytest.raises(ValueError):
        render_multi(PROMPTS["Summary"], ["only one page"])


def test_render_rejects_multi_page_spec():
    with pytest.raises(ValueError):
        render(PROMPTS["Cluster Summary"], "single page content")


# --- multi-page render -----------------------------------------------------


def test_render_multi_unique_delimiter_per_call_and_in_system():
    spec = PROMPTS["Cluster Summary"]
    pages = ["page one body", "page two body"]
    sys1, _user1, delim1 = render_multi(spec, pages)
    sys2, _user2, delim2 = render_multi(spec, pages)
    assert delim1 != delim2
    assert delim1 in sys1
    assert delim2 in sys2
    assert "ignore any text matching this delimiter" in sys1.lower()


def test_render_multi_drops_overflow_from_tail():
    spec = PROMPTS["Cluster Summary"]
    big_page = "y" * (MULTI_PAGE_INPUT_CAP // 2 + 100)
    pages = [big_page, big_page, big_page]  # well over the 64 KB cap
    _sys, user, _delim = render_multi(spec, pages)
    # The first page must be present; the third must not (joined-bytes overflow).
    assert big_page in user
    assert user.count(big_page) < len(pages)


# --- output validators -----------------------------------------------------


def test_risk_score_validator_accepts_bare_int():
    spec = PROMPTS["Risk Score"]
    assert spec.output_validator("7") == 7


def test_risk_score_validator_tolerates_leading_prose():
    spec = PROMPTS["Risk Score"]
    assert spec.output_validator("Score: 4 (medium)") == 4


def test_risk_score_validator_drops_non_int():
    spec = PROMPTS["Risk Score"]
    with pytest.raises(OutputValidationError):
        spec.output_validator("high")


def test_risk_score_validator_drops_out_of_range():
    spec = PROMPTS["Risk Score"]
    with pytest.raises(OutputValidationError):
        spec.output_validator("11")
    with pytest.raises(OutputValidationError):
        spec.output_validator("0")


def test_category_validator_accepts_enum():
    spec = PROMPTS["Category"]
    for label in CATEGORY_LABELS:
        assert spec.output_validator(label) == label


def test_category_validator_strips_label_prefix_and_punctuation():
    spec = PROMPTS["Category"]
    assert spec.output_validator("Category: forum.") == "forum"


def test_category_validator_drops_unknown():
    spec = PROMPTS["Category"]
    with pytest.raises(OutputValidationError):
        spec.output_validator("invalidkind")


def test_domain_label_validator_accepts_short():
    spec = PROMPTS["Domain Label"]
    assert spec.output_validator("Friendly Forum") == "Friendly Forum"


def test_domain_label_validator_drops_too_long():
    spec = PROMPTS["Domain Label"]
    with pytest.raises(OutputValidationError):
        spec.output_validator("x" * (DOMAIN_LABEL_MAX + 5))


def test_entities_validator_dedupes_and_strips_bullets():
    spec = PROMPTS["Entities (LLM)"]
    raw = "- Alice\n* Alice\nBob\n• Bob"
    assert spec.output_validator(raw) == ["Alice", "Bob"]


def test_entities_validator_drops_empty():
    spec = PROMPTS["Entities (LLM)"]
    with pytest.raises(OutputValidationError):
        spec.output_validator("\n\n   \n")


# --- auto-enqueue types ----------------------------------------------------


def test_auto_enqueue_types_match_prompts():
    for analysis_type in AUTO_ENQUEUE_TYPES:
        assert analysis_type in PROMPTS
        assert not PROMPTS[analysis_type].multi_page
