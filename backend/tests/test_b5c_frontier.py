"""Phase B5c — per-crawl link frontier + watchlist matcher.

Frontier tests are pure: build a ``Frontier``, enqueue some URLs, assert the
pop order matches the spec for that mode (PLAN.md:285). The matcher tests
pin the case-insensitive multi-term behaviour required by Focused mode and
the watchlist auto-flag (PLAN.md:286).
"""
from __future__ import annotations

from backend.crawler.frontier import Frontier, WatchlistMatcher


ONION_A = "http://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.onion/"
ONION_B = "http://bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.onion/"
ONION_C = "http://cccccccccccccccccccccccccccccccccccccccccccccccccccccccc.onion/"


# ---------------------------------------------------------------------------
# Frontier
# ---------------------------------------------------------------------------


def test_frontier_bfs_returns_fifo_order():
    q = Frontier(mode="BFS", seed_host="x")
    assert q.enqueue(ONION_A, depth=0)
    assert q.enqueue(ONION_B, depth=1)
    assert q.enqueue(ONION_C, depth=1)
    assert q.pop().url == ONION_A
    assert q.pop().url == ONION_B
    assert q.pop().url == ONION_C
    assert q.pop() is None


def test_frontier_dfs_returns_lifo_order():
    q = Frontier(mode="DFS", seed_host="x")
    q.enqueue(ONION_A, depth=0)
    q.enqueue(ONION_B, depth=1)
    q.enqueue(ONION_C, depth=2)
    assert q.pop().url == ONION_C
    assert q.pop().url == ONION_B
    assert q.pop().url == ONION_A


def test_frontier_dedupes_seen_urls():
    q = Frontier(mode="BFS", seed_host="x")
    assert q.enqueue(ONION_A, depth=0) is True
    # Second enqueue is a no-op.
    assert q.enqueue(ONION_A, depth=1) is False
    assert q.pop().url == ONION_A
    assert q.pop() is None


def test_frontier_enforces_max_depth():
    q = Frontier(mode="BFS", seed_host="x", max_depth=2)
    assert q.enqueue(ONION_A, depth=2) is True
    assert q.enqueue(ONION_B, depth=3) is False


def test_frontier_diverse_round_robins_across_hosts():
    host_a = "a" * 56 + ".onion"
    host_b = "b" * 56 + ".onion"
    q = Frontier(mode="Diverse", seed_host=host_a)
    a1 = f"http://{host_a}/one"
    a2 = f"http://{host_a}/two"
    b1 = f"http://{host_b}/one"
    b2 = f"http://{host_b}/two"
    q.enqueue(a1, depth=1)
    q.enqueue(a2, depth=1)
    q.enqueue(b1, depth=1)
    q.enqueue(b2, depth=1)
    hosts = [q.pop().host for _ in range(4)]
    # First two pops cover both hosts before either host's second URL.
    assert set(hosts[:2]) == {host_a, host_b}
    assert set(hosts[2:]) == {host_a, host_b}


def test_frontier_cross_site_prefers_cross_host_then_drains_seed_host():
    seed_host = "a" * 56 + ".onion"
    q = Frontier(mode="Cross-site", seed_host=seed_host)
    same_host = f"http://{seed_host}/same"
    cross_host_1 = f"http://{'b' * 56}.onion/"
    cross_host_2 = f"http://{'c' * 56}.onion/"
    q.enqueue(same_host, depth=1)
    q.enqueue(cross_host_1, depth=1)
    q.enqueue(cross_host_2, depth=1)
    assert q.pop().url == cross_host_1
    assert q.pop().url == cross_host_2
    # Only after the cross-host fringe drains do we drop into seed-host.
    assert q.pop().url == same_host


def test_frontier_focused_drops_ineligible_children():
    q = Frontier(mode="Focused", seed_host="x")
    # Seed is always eligible (the runtime calls enqueue with the default).
    assert q.enqueue(ONION_A, depth=0) is True
    # Parent didn't match watchlist → child is filtered.
    assert q.enqueue(ONION_B, depth=1, focused_eligible=False) is False
    # Eligible child survives.
    assert q.enqueue(ONION_C, depth=1, focused_eligible=True) is True


# ---------------------------------------------------------------------------
# WatchlistMatcher
# ---------------------------------------------------------------------------


def test_matcher_case_insensitive():
    m = WatchlistMatcher(["FraudList", "ransomware"])
    out = m.match("Today's FRAUDLIST contains new entries. ransomware too.")
    assert set(out) == {"FraudList", "ransomware"}


def test_matcher_dedupes_repeated_hits():
    m = WatchlistMatcher(["alpha"])
    out = m.match("alpha alpha ALPHA alpha")
    assert out == ["alpha"]


def test_matcher_empty_terms_returns_empty_matches():
    m = WatchlistMatcher([])
    assert m.empty is True
    assert m.match("anything") == []


def test_matcher_ignores_whitespace_only_and_non_string_terms():
    m = WatchlistMatcher(["   ", "", "ok"])  # type: ignore[list-item]
    assert m.match("contains ok") == ["ok"]


def test_matcher_preserves_first_occurrence_order():
    m = WatchlistMatcher(["beta", "alpha"])
    out = m.match("alpha appears first then beta later")
    assert out == ["alpha", "beta"]
