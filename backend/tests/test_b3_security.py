"""Phase B3 — security utilities: net, paths, settings validators."""
from __future__ import annotations

import asyncio
import os
import socket
import stat
import subprocess
import unicodedata
from pathlib import Path
from unittest.mock import patch

import aiohttp
import pytest
from aiohttp_socks import ProxyConnector

from backend.db.settings import SETTING_VALIDATORS, get_setting, put_setting
from backend.security import net, paths
from backend.security.net import (
    ConfigError,
    EgressError,
    is_loopback_host,
    make_session,
    make_tor_session,
    network_of_host,
    network_of_url,
    validate_i2p_host,
    validate_i2p_proxy,
    validate_i2p_url,
    validate_network_url,
    validate_onion_host,
    validate_onion_url,
    validate_tor_proxy,
)
from backend.security.paths import (
    PathError,
    create_project_root,
    launch_browser,
    open_under,
    project_path,
    projects_base,
    safe_realpath_under,
    secure_temp_file,
    validate_browser_path,
    validate_db_relpath,
    validate_home,
    validate_project_name,
    write_sensitive_file,
)


# A real v3 onion fixture (DuckDuckGo). 56 chars of base32, exactly.
ONION_56 = "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczyd.onion"

# An ``.i2p`` b32 destination fixture: 52 chars of base32 + ``.b32.i2p``.
I2P_B32 = ("a" * 52) + ".b32.i2p"
# An address-book name (not self-authenticating, but a valid intake form).
I2P_NAME = "forum.i2p"


# =============================================================================
# security.net
# =============================================================================


class TestTorProxyValidator:
    @pytest.mark.parametrize("value", [
        "socks5h://127.0.0.1:9050",
        "socks5h://127.0.0.1:9150",
        "socks5h://::1:9050",
    ])
    def test_accepts_loopback_socks5h(self, value):
        assert validate_tor_proxy(value) == value

    def test_strips_whitespace(self):
        assert validate_tor_proxy("  socks5h://127.0.0.1:9050\n") == "socks5h://127.0.0.1:9050"

    @pytest.mark.parametrize("value", [
        "",
        "socks5://127.0.0.1:9050",                # no h — DNS leak
        "socks5h://localhost:9050",               # localhost — DNS-rebind risk
        "socks5h://10.0.0.1:9050",                # non-loopback
        "socks5h://127.0.0.1",                    # missing port
        "http://127.0.0.1:9050",                  # wrong scheme
        "socks5h://127.0.0.1:9050/extra",         # trailing garbage
        "socks5h://127.0.0.1:0",                  # port 0 — invalid
        "socks5h://127.0.0.1:65536",              # > 65535
        "socks5h://127.0.0.1:99999",              # 5 digits but oob
        "socks5h://127.0.0.1:00080",              # leading zero
    ])
    def test_rejects_non_loopback_socks5h(self, value):
        with pytest.raises(ConfigError):
            validate_tor_proxy(value)

    @pytest.mark.parametrize("port", ["1", "80", "9050", "9150", "65535"])
    def test_accepts_full_valid_port_range(self, port):
        url = f"socks5h://127.0.0.1:{port}"
        assert validate_tor_proxy(url) == url

    def test_rejects_non_string(self):
        with pytest.raises(ConfigError):
            validate_tor_proxy(None)  # type: ignore[arg-type]


class TestOnionValidators:
    def test_accepts_v3_onion_host(self):
        assert validate_onion_host(ONION_56) == ONION_56

    def test_lowercases_onion_host(self):
        assert validate_onion_host(ONION_56.upper()) == ONION_56

    @pytest.mark.parametrize("host", [
        "expyuzz4wqqyqhjn.onion",                 # v2 (16-char)
        "duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczyd",  # missing .onion
        "1.2.3.4",
        "example.com",
        "duckduckgo!gg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczyd.onion",  # non-base32 char
    ])
    def test_rejects_bad_onion_hosts(self, host):
        with pytest.raises(EgressError):
            validate_onion_host(host)

    def test_accepts_v3_onion_url_with_port_and_path(self):
        url = f"https://{ONION_56}:8443/some/path?x=1#frag"
        assert validate_onion_url(url) == url

    @pytest.mark.parametrize("url", [
        "ftp://" + ONION_56,
        "http://example.com",
        "http://" + ONION_56[:-1] + ".onion",  # 55 chars before .onion
        "",
        f"https://{ONION_56}:0/",                # port 0 — invalid
        f"https://{ONION_56}:65536/",            # > 65535
        f"https://{ONION_56}:99999/",            # 5 digits but oob
    ])
    def test_rejects_bad_onion_urls(self, url):
        with pytest.raises(EgressError):
            validate_onion_url(url)

    @pytest.mark.parametrize("port", ["1", "80", "443", "8443", "65535"])
    def test_accepts_full_valid_port_range(self, port):
        url = f"https://{ONION_56}:{port}/x"
        assert validate_onion_url(url) == url


class TestI2pValidators:
    @pytest.mark.parametrize("host", [I2P_B32, I2P_NAME, "sub.forum.i2p"])
    def test_accepts_name_and_b32_forms(self, host):
        assert validate_i2p_host(host) == host

    def test_lowercases_i2p_host(self):
        assert validate_i2p_host(I2P_NAME.upper()) == I2P_NAME

    @pytest.mark.parametrize("host", [
        ONION_56,            # wrong network
        "example.com",
        "forum.i2p.evil",    # suffix not last
        "forum.onion",
        "",
    ])
    def test_rejects_non_i2p_hosts(self, host):
        with pytest.raises(EgressError):
            validate_i2p_host(host)

    def test_accepts_i2p_url_with_port_and_path(self):
        url = f"http://{I2P_NAME}:8080/some/path?x=1#frag"
        assert validate_i2p_url(url) == url

    @pytest.mark.parametrize("url", [
        "ftp://" + I2P_NAME,
        "http://example.com",
        "http://" + ONION_56 + "/",   # wrong network
        "",
    ])
    def test_rejects_bad_i2p_urls(self, url):
        with pytest.raises(EgressError):
            validate_i2p_url(url)


class TestI2pProxyValidator:
    @pytest.mark.parametrize("value", [
        "socks5h://127.0.0.1:4447",
        "socks5h://::1:4447",
    ])
    def test_accepts_loopback_socks5h(self, value):
        assert validate_i2p_proxy(value) == value

    @pytest.mark.parametrize("value", [
        "socks5://127.0.0.1:4447",       # no h — DNS leak
        "http://127.0.0.1:4444",         # wrong scheme
        "socks5h://10.0.0.1:4447",       # non-loopback
        "socks5h://localhost:4447",      # localhost — rebind risk
        "",
    ])
    def test_rejects_bad_i2p_proxies(self, value):
        with pytest.raises(ConfigError):
            validate_i2p_proxy(value)


class TestNetworkDispatch:
    def test_network_of_host(self):
        assert network_of_host(ONION_56) == "tor"
        assert network_of_host(I2P_B32) == "i2p"
        assert network_of_host(I2P_NAME) == "i2p"

    def test_network_of_host_rejects_clearnet(self):
        with pytest.raises(EgressError):
            network_of_host("example.com")

    def test_network_of_url(self):
        assert network_of_url(f"http://{ONION_56}/") == "tor"
        assert network_of_url(f"http://{I2P_NAME}/x") == "i2p"

    def test_validate_network_url_dispatches(self):
        ou = f"https://{ONION_56}/x"
        iu = f"http://{I2P_NAME}/x"
        assert validate_network_url(ou) == ("tor", ou)
        assert validate_network_url(iu) == ("i2p", iu)

    def test_validate_network_url_rejects_clearnet(self):
        with pytest.raises(EgressError):
            validate_network_url("http://example.com/")


class TestMakeSessionI2p:
    @pytest.fixture
    def i2p_proxy(self):
        return "socks5h://127.0.0.1:4447"

    def test_i2p_target_uses_socks_proxy_connector(self, i2p_proxy):
        async def go():
            s = make_session(I2P_B32, proxy=i2p_proxy)
            try:
                assert isinstance(s.connector, ProxyConnector)
            finally:
                await s.close()
        asyncio.run(go())

    def test_i2p_session_has_no_socks_credentials(self, i2p_proxy):
        """I2P has no per-stream circuit isolation, so no SOCKS auth is set —
        unlike onion hosts which key auth on the host for circuit isolation."""
        async def go():
            s = make_session(I2P_NAME, proxy=i2p_proxy)
            try:
                conn = s.connector
                assert isinstance(conn, ProxyConnector)
                assert conn._proxy_username is None
                assert conn._proxy_password is None
            finally:
                await s.close()
        asyncio.run(go())

    def test_i2p_connector_resolves_remote(self, i2p_proxy):
        """rdns=True keeps ``.i2p`` resolution router-side (no OS DNS leak)."""
        async def go():
            s = make_session(I2P_B32, proxy=i2p_proxy)
            try:
                assert s.connector._rdns is True
            finally:
                await s.close()
        asyncio.run(go())


class TestLoopbackHost:
    @pytest.mark.parametrize("h", ["127.0.0.1", "::1"])
    def test_literal_loopbacks_only(self, h):
        assert is_loopback_host(h) is True

    @pytest.mark.parametrize("h", ["localhost", "127.0.0.2", "0.0.0.0", "", None])
    def test_localhost_is_not_loopback(self, h):
        # DNS-rebind defense: "localhost" must not be treated as loopback.
        assert is_loopback_host(h) is False


class TestMakeTorSession:
    @pytest.fixture
    def valid_proxy(self):
        return "socks5h://127.0.0.1:9050"

    def test_loopback_target_uses_plain_tcp_connector(self, valid_proxy):
        async def go():
            s = make_tor_session("127.0.0.1", proxy=valid_proxy)
            try:
                assert isinstance(s.connector, aiohttp.TCPConnector)
                assert not isinstance(s.connector, ProxyConnector)
            finally:
                await s.close()
        asyncio.run(go())

    def test_onion_target_uses_socks_proxy_connector(self, valid_proxy):
        async def go():
            s = make_tor_session(ONION_56, proxy=valid_proxy)
            try:
                assert isinstance(s.connector, ProxyConnector)
            finally:
                await s.close()
        asyncio.run(go())

    def test_clearnet_target_blocked(self, valid_proxy):
        with pytest.raises(EgressError):
            make_tor_session("example.com", proxy=valid_proxy)

    def test_localhost_target_blocked(self, valid_proxy):
        # "localhost" is not in LOOPBACK_HOSTS, so it falls through to the
        # onion validator and fails.
        with pytest.raises(EgressError):
            make_tor_session("localhost", proxy=valid_proxy)

    def test_bad_proxy_rejected_at_construction(self):
        with pytest.raises(ConfigError):
            make_tor_session(ONION_56, proxy="socks5://1.2.3.4:9050")

    def test_non_loopback_proxy_rejected(self):
        with pytest.raises(ConfigError):
            make_tor_session(ONION_56, proxy="socks5h://10.0.0.1:9050")

    def test_onion_session_uses_tor_browser_request_profile(self, valid_proxy):
        """Onion egress carries the Tor Browser header set, not a tool name."""
        async def go():
            s = make_tor_session(ONION_56, proxy=valid_proxy)
            try:
                headers = s._default_headers
                ua = headers.get("User-Agent", "")
                # Mimics Tor Browser (Firefox ESR); never names the tool —
                # a unique tool name is a permanent fingerprint.
                assert "Firefox" in ua and "Gecko" in ua
                assert "rabbithole" not in ua.lower()
                # A realistic browser header set, not the old 2-header request.
                assert "Accept-Language" in headers
                assert headers.get("Sec-Fetch-Mode") == "navigate"
                assert headers.get("Upgrade-Insecure-Requests") == "1"
                enc = headers.get("Accept-Encoding", "")
                assert "gzip" in enc and "deflate" in enc
                # `br` is advertised only when aiohttp can decompress it.
                assert ("br" in enc) == net._HAS_BROTLI
            finally:
                await s.close()
        asyncio.run(go())

    def test_onion_session_isolates_circuit_per_onion_host(self, valid_proxy):
        """SOCKS auth is keyed on the onion host → one Tor circuit per site."""
        async def go():
            s = make_tor_session(ONION_56, proxy=valid_proxy)
            try:
                conn = s.connector
                assert isinstance(conn, ProxyConnector)
                assert conn._proxy_username == ONION_56
                assert conn._proxy_password == ONION_56
            finally:
                await s.close()
        asyncio.run(go())

    def test_distinct_onion_hosts_get_distinct_socks_credentials(self, valid_proxy):
        """Two different onion hosts must not share a SOCKS auth pair —
        otherwise they could ride the same Tor circuit."""
        other = "abacus" * 9 + "22" + ".onion"
        async def go():
            s1 = make_tor_session(ONION_56, proxy=valid_proxy)
            s2 = make_tor_session(other, proxy=valid_proxy)
            try:
                assert s1.connector._proxy_username != s2.connector._proxy_username
            finally:
                await s1.close()
                await s2.close()
        asyncio.run(go())


# =============================================================================
# security.paths — home + project resolution
# =============================================================================


class TestProjectName:
    @pytest.mark.parametrize("name", [
        "scratch",
        "My Project",
        "case_42.v1",
        "a",
        "Aa-_.0" * 10 + "x",  # exactly 61 chars — well under 64
    ])
    def test_accepts_valid_names(self, name):
        assert validate_project_name(name) == name

    @pytest.mark.parametrize("name", [
        "",
        "..",
        "../etc",
        "name/with/slash",
        "name\x00null",
        "name\nnewline",
        "a" * 65,                  # 65 chars — too long
        "weird:name",
        "tab\there",
    ])
    def test_rejects_invalid_names(self, name):
        with pytest.raises(PathError):
            validate_project_name(name)

    def test_nfc_normalization_rejects_non_ascii(self):
        # The spec regex is ASCII-only (PLAN.md:243). Non-ASCII names are
        # rejected even when their NFC form differs from the input.
        composed = "café"             # "caf" + U+00E9
        decomposed = "café"          # "cafe" + combining acute
        with pytest.raises(PathError):
            validate_project_name(composed)
        with pytest.raises(PathError):
            validate_project_name(decomposed)
        # Sanity: both forms canonicalize to the same string under NFC.
        assert unicodedata.normalize("NFC", decomposed) == composed


class TestHomeAndProjectsBase:
    def test_validate_home_rejects_unset_home(self, monkeypatch):
        monkeypatch.delenv("HOME", raising=False)
        with pytest.raises(PathError):
            validate_home()

    def test_validate_home_rejects_missing_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path / "does-not-exist"))
        with pytest.raises(PathError):
            validate_home()

    def test_projects_base_lives_under_home(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        base = projects_base()
        assert base == tmp_path / ".local" / "share" / "rabbithole" / "projects"

    def test_project_path_uses_validated_name(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        assert project_path("scratch") == projects_base() / "scratch"

    def test_project_path_rejects_traversal(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        with pytest.raises(PathError):
            project_path("../etc")


class TestCreateProjectRoot:
    def test_creates_with_0700_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        p = create_project_root("scratch")
        assert p.is_dir()
        assert stat.S_IMODE(p.stat().st_mode) == 0o700

    def test_idempotent_reasserts_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        p = create_project_root("scratch")
        os.chmod(p, 0o755)
        assert stat.S_IMODE(p.stat().st_mode) == 0o755
        create_project_root("scratch")
        assert stat.S_IMODE(p.stat().st_mode) == 0o700


class TestSafeRealpathUnder:
    def test_accepts_path_inside_base(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()
        target = base / "child"
        target.touch()
        out = safe_realpath_under(base, target)
        assert out == target.resolve()

    def test_rejects_symlink_pointing_outside(self, tmp_path):
        base = tmp_path / "base"
        outside = tmp_path / "outside"
        base.mkdir()
        outside.mkdir()
        (outside / "secret").touch()
        link = base / "pivot"
        link.symlink_to(outside / "secret")
        with pytest.raises(PathError):
            safe_realpath_under(base, link)

    def test_open_under_uses_canonical_path(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()
        target = base / "data.txt"
        target.write_bytes(b"hello")
        with open_under(base, target, "rb") as fh:
            assert fh.read() == b"hello"


class TestValidateDbRelpath:
    """``validate_db_relpath`` is the gate between the registry and on-disk
    DB files. Symlinks at the final component must be refused even when the
    realpath target is itself inside the projects base — otherwise an
    attacker who can drop a symlink under the base can pivot one project's
    DB handle at another (Codex Sec 1, 2026-05-12)."""

    @pytest.fixture
    def base(self, tmp_path, monkeypatch):
        target = tmp_path / "projects"
        target.mkdir()
        monkeypatch.setattr(paths, "projects_base", lambda: target)
        monkeypatch.setenv("HOME", str(tmp_path))
        return target

    def test_accepts_plain_relative_db_under_base(self, base):
        real = base / "alpha.db"
        real.write_bytes(b"")
        assert validate_db_relpath("alpha.db") == real.resolve()

    def test_rejects_in_base_symlink_pointing_at_another_in_base_db(self, base):
        """Final-component symlink between two in-base DBs — the lstat-on-
        canonical check (pre-fix) silently accepted this because realpath
        resolved the link away before the symlink check ran."""
        real = base / "alpha.db"
        real.write_bytes(b"")
        link = base / "pivot.db"
        link.symlink_to(real)
        with pytest.raises(PathError, match="symlink"):
            validate_db_relpath("pivot.db")

    def test_rejects_absolute_symlink_inside_home_pointing_at_in_base_db(
        self, base, tmp_path
    ):
        real = base / "alpha.db"
        real.write_bytes(b"")
        link = tmp_path / "pivot.db"
        link.symlink_to(real)
        with pytest.raises(PathError, match="symlink"):
            validate_db_relpath(str(link))

    def test_rejects_traversal_segment(self, base):
        with pytest.raises(PathError, match="traversal"):
            validate_db_relpath("../escape.db")

    def test_rejects_non_db_suffix(self, base):
        with pytest.raises(PathError, match=r"end in \.db"):
            validate_db_relpath("alpha.sqlite")

    def test_rejects_irregular_file_at_final_component(self, base):
        # Directory at the would-be DB location — must not be accepted as a
        # DB file even though its name ends in .db.
        (base / "alpha.db").mkdir()
        with pytest.raises(PathError, match="regular file"):
            validate_db_relpath("alpha.db")


# =============================================================================
# security.paths — browser
# =============================================================================


@pytest.fixture
def fake_browser(tmp_path, monkeypatch):
    """Create a fake Tor Browser launcher executable + monkeypatch the
    allowlist to accept its parent dir."""
    base = tmp_path / "tor-browser"
    base.mkdir()
    launcher = base / "start-tor-browser"
    launcher.write_text("#!/bin/sh\nexit 0\n")
    os.chmod(launcher, 0o755)
    monkeypatch.setattr(paths, "browser_base_paths", lambda: [base.resolve()])
    return launcher


class TestValidateBrowserPath:
    def test_accepts_executable_under_allowlist(self, fake_browser):
        out = validate_browser_path(str(fake_browser))
        assert out == fake_browser.resolve()

    def test_rejects_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "browser_base_paths", lambda: [tmp_path])
        with pytest.raises(PathError):
            validate_browser_path(str(tmp_path / "missing"))

    def test_rejects_non_executable(self, fake_browser):
        os.chmod(fake_browser, 0o644)
        with pytest.raises(PathError):
            validate_browser_path(str(fake_browser))

    def test_rejects_directory(self, fake_browser):
        with pytest.raises(PathError):
            validate_browser_path(str(fake_browser.parent))

    def test_rejects_outside_allowlist(self, fake_browser, tmp_path, monkeypatch):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        evil = elsewhere / "fake-browser"
        evil.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(evil, 0o755)
        # Allowlist still points at fake_browser's parent only.
        with pytest.raises(PathError):
            validate_browser_path(str(evil))

    def test_rejects_symlink_at_final_component(self, fake_browser, tmp_path):
        link = fake_browser.parent / "link-to-browser"
        link.symlink_to(fake_browser)
        with pytest.raises(PathError):
            validate_browser_path(str(link))

    def test_rejects_non_string(self):
        with pytest.raises(PathError):
            validate_browser_path(None)  # type: ignore[arg-type]


class TestLaunchBrowser:
    def test_popen_called_with_correct_argv_and_no_shell(self, fake_browser):
        url = f"http://{ONION_56}/path"
        with patch.object(subprocess, "Popen") as popen:
            popen.return_value = object()
            launch_browser(str(fake_browser), url)
        assert popen.called
        args, kwargs = popen.call_args
        argv = args[0]
        assert argv == [str(fake_browser.resolve()), "--", url]
        assert "shell" not in kwargs  # default False
        assert kwargs.get("close_fds") is True
        assert kwargs.get("stdin") is subprocess.DEVNULL
        assert kwargs.get("stdout") is subprocess.DEVNULL
        assert kwargs.get("stderr") is subprocess.DEVNULL
        env = kwargs["env"]
        assert env["PATH"] == "/usr/bin:/bin"
        assert env["LANG"] == "C"
        assert env["LC_ALL"] == "C"
        # No leaking parent env not on the forwardable allowlist:
        for key in env:
            assert key in {
                "PATH", "LANG", "LC_ALL",
                "DISPLAY", "XAUTHORITY",
                "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
            }

    def test_url_must_be_onion(self, fake_browser):
        with pytest.raises(EgressError):
            launch_browser(str(fake_browser), "https://example.com")

    def test_toctou_symlink_swap_refused(self, fake_browser):
        """Save a valid path → swap the file for a symlink before launch →
        launch must refuse (PLAN.md:247)."""
        url = f"http://{ONION_56}/"
        # First confirm it would work.
        with patch.object(subprocess, "Popen") as popen:
            popen.return_value = object()
            launch_browser(str(fake_browser), url)

        # Now swap: replace the executable with a symlink to another file.
        target = fake_browser.parent / "decoy"
        target.write_text("#!/bin/sh\nexit 0\n")
        os.chmod(target, 0o755)
        fake_browser.unlink()
        fake_browser.symlink_to(target)

        with pytest.raises(PathError):
            launch_browser(str(fake_browser), url)


# =============================================================================
# security.paths — sensitive file writes
# =============================================================================


class TestSensitiveFileWrites:
    def test_write_sensitive_file_is_0600(self, tmp_path):
        target = tmp_path / "data.bin"
        write_sensitive_file(target, b"secret")
        assert target.read_bytes() == b"secret"
        assert stat.S_IMODE(target.stat().st_mode) == 0o600

    def test_write_sensitive_file_refuses_symlink(self, tmp_path):
        real = tmp_path / "real.bin"
        real.write_bytes(b"untouched")
        target = tmp_path / "link.bin"
        target.symlink_to(real)
        with pytest.raises(OSError):  # ELOOP from O_NOFOLLOW
            write_sensitive_file(target, b"new content")
        # The real file is unchanged.
        assert real.read_bytes() == b"untouched"

    def test_secure_temp_file_is_0600_and_deletes(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        with secure_temp_file(suffix=".tmp") as p:
            assert p.exists()
            assert stat.S_IMODE(p.stat().st_mode) == 0o600
            held = p
        assert not held.exists()

    def test_secure_temp_file_honors_custom_dir(self, tmp_path):
        with secure_temp_file(suffix=".tmp", dir=tmp_path) as p:
            assert p.parent == tmp_path
            assert stat.S_IMODE(p.stat().st_mode) == 0o600


# =============================================================================
# db.settings dispatch
# =============================================================================


class TestSettingValidators:
    def test_tor_proxy_validator_registered(self):
        assert "tor.proxy" in SETTING_VALIDATORS
        assert SETTING_VALIDATORS["tor.proxy"]("socks5h://127.0.0.1:9050") == "socks5h://127.0.0.1:9050"

    def test_put_setting_round_trips_tor_proxy(self, db):
        out = put_setting(db, "tor.proxy", "socks5h://127.0.0.1:9150")
        assert out == "socks5h://127.0.0.1:9150"
        assert get_setting(db, "tor.proxy") == "socks5h://127.0.0.1:9150"

    def test_put_setting_rejects_bad_tor_proxy(self, db):
        with pytest.raises(ConfigError):
            put_setting(db, "tor.proxy", "http://evil:9050")
        # Stored value still the default seeded by CrawlDB._seed_defaults.
        assert get_setting(db, "tor.proxy") == "socks5h://127.0.0.1:9050"

    def test_put_setting_rejects_unknown_key(self, db):
        with pytest.raises(ValueError):
            put_setting(db, "unknown.flag", "true")


# =============================================================================
# socket.getaddrinfo guard — proves the conftest fixture is wired
# =============================================================================


class TestGetaddrinfoBan:
    def test_fixture_blows_up_on_call(self):
        with pytest.raises(AssertionError) as excinfo:
            socket.getaddrinfo("example.com", 80)
        assert "getaddrinfo" in str(excinfo.value)

    def test_make_tor_session_does_not_resolve_dns(self):
        """Constructing the session must not trigger any DNS lookup —
        SOCKS5h is supposed to do resolution Tor-side."""

        async def go():
            s = make_tor_session(ONION_56, proxy="socks5h://127.0.0.1:9050")
            try:
                # If we got here without AssertionError, getaddrinfo wasn't called.
                assert s is not None
            finally:
                await s.close()
        asyncio.run(go())
