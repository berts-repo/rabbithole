"""Project paths, file permissions, and the Tor Browser launcher.

This module owns every path-touching operation that needs to stay inside
the analyst's home directory or the project tree. Every public function
re-validates ``$HOME`` before doing anything else — a stripped or spoofed
``HOME`` cannot redirect us. After ``realpath`` we always re-check that the
canonical path still sits under the validated base (TOCTOU close-out per
PLAN.md:245); browser launches re-validate the path at exec time so a
symlink swap between settings save and click does not let us exec an
attacker-controlled binary.

File-permission posture:

  * Project root directories: 0700 (PLAN.md:252).
  * Project DB / sensitive files: 0600.
  * Temp files: 0600 + delete-on-exit, default placed under the project
    root so they inherit the same surrounding ACLs.
"""
from __future__ import annotations

import contextlib
import os
import re
import stat
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Iterator

from .net import validate_onion_url


class PathError(ValueError):
    """Raised for any path / browser / permissions violation."""


# Project names are stored NFC-normalized and must match this regex.
# Mirrors PLAN.md:243.
PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9 ._\-]{1,64}$")

# Per the Linux test host. macOS/Windows entries are kept so the same code
# is portable; on a system where they do not exist, ``Path.resolve`` will
# simply not produce a match and the validator will refuse the path.
_BROWSER_BASE_HINTS: tuple[Path, ...] = (
    # Linux: traditional unpacked tar location in $HOME.
    Path("~/tor-browser").expanduser(),
    # Linux: ``torbrowser-launcher`` (Debian/Ubuntu/Parrot apt package)
    # downloads here. Architecture-suffixed; we cover x86_64 today,
    # other arches can be added when we encounter them.
    Path("~/.local/share/torbrowser/tbb/x86_64/tor-browser").expanduser(),
    # Linux: distro / sysadmin install.
    Path("/opt/tor-browser"),
    # macOS bundle root.
    Path("/Applications/Tor Browser.app"),
)

# Canonical executable paths under the install hints above. Used by
# ``discover_browser_path`` so the default Tor Browser install works
# out of the box when ``browser.path`` is unset. Each entry still has
# to pass ``validate_browser_path`` (lstat, allowlist containment,
# executable bit) — discovery does not relax that posture.
_BROWSER_EXEC_HINTS: tuple[Path, ...] = (
    Path("~/tor-browser/Browser/start-tor-browser").expanduser(),
    Path(
        "~/.local/share/torbrowser/tbb/x86_64/tor-browser/Browser/start-tor-browser"
    ).expanduser(),
    Path("/opt/tor-browser/Browser/start-tor-browser"),
    Path("/Applications/Tor Browser.app/Contents/MacOS/firefox"),
)

# DISPLAY values look like ":0", ":0.0", ":10", etc. Anything else (a path,
# a hostname, a metachar) is rejected — we will not forward it into Popen.
_DISPLAY_RE = re.compile(r"^:\d+(\.\d+)?$")


# --- Home + project base ----------------------------------------------------


def validate_home() -> Path:
    """Return the analyst's home dir if ``$HOME`` is set, exists, is a
    directory, and is owned by the current user. Raise ``PathError`` otherwise.
    """
    raw = os.environ.get("HOME")
    if not raw:
        raise PathError("HOME is not set")
    home = Path(raw)
    if not home.is_dir():
        raise PathError(f"HOME is not a directory: {home}")
    if hasattr(os, "geteuid"):
        st = home.stat()
        if st.st_uid != os.geteuid():
            raise PathError(f"HOME is not owned by current user: {home}")
    return home


def projects_base() -> Path:
    """``~/.local/share/rabbithole/projects/`` — always re-derived from a
    freshly validated ``$HOME``."""
    return validate_home() / ".local" / "share" / "rabbithole" / "projects"


# --- Project naming + path resolution ---------------------------------------


def validate_project_name(name: object) -> str:
    """NFC-normalize ``name`` and ensure it matches ``PROJECT_NAME_RE``."""
    if not isinstance(name, str):
        raise PathError(f"project name must be a string, got {type(name).__name__}")
    normalized = unicodedata.normalize("NFC", name)
    if not PROJECT_NAME_RE.match(normalized):
        raise PathError(
            "project name must be 1–64 chars of [A-Za-z0-9 ._-], got "
            f"{name!r}"
        )
    # Pure-dot names ("." / "..") would survive the regex above but are
    # traversal sentinels at the filesystem level — reject explicitly.
    if normalized.strip(".") == "":
        raise PathError(f"project name is a path sentinel: {name!r}")
    return normalized


def project_path(name: str) -> Path:
    """Resolve ``<projects_base>/<name>`` after validating both sides.

    The path is **not** required to exist — this is also used to compute
    the location for a project that is about to be created. Containment is
    re-checked via ``safe_realpath_under`` on creation and on every open.
    """
    base = projects_base()
    return base / validate_project_name(name)


def create_project_root(name: str) -> Path:
    """Create the project directory tree with mode 0o700 and return it.

    Idempotent: if the leaf already exists we still re-apply 0o700. Parent
    directories are created with the umask in effect; we only constrain
    the leaf because the parent (`.local/share/rabbithole/projects`) is
    shared across projects.
    """
    target = project_path(name)
    target.mkdir(parents=True, exist_ok=True)
    os.chmod(target, 0o700)
    # Containment check — guards against a symlink poisoned parent.
    safe_realpath_under(projects_base(), target)
    return target


# --- Containment-safe path resolution ---------------------------------------


def safe_realpath_under(base: Path, target: Path) -> Path:
    """``realpath`` both arguments and confirm the resolved target sits
    under the resolved base. Returns the canonical target. Raises
    ``PathError`` on escape.

    Uses ``Path.resolve(strict=False)`` so this works for paths that are
    about to be created. Callers that need the file to exist should call
    ``Path.is_file()``/``is_dir()`` themselves after.
    """
    base_resolved = Path(os.path.realpath(base))
    target_resolved = Path(os.path.realpath(target))
    try:
        target_resolved.relative_to(base_resolved)
    except ValueError:
        raise PathError(
            f"path {target!r} resolves outside base {base!r} "
            f"(canonical: {target_resolved} not under {base_resolved})"
        ) from None
    return target_resolved


@contextlib.contextmanager
def open_under(base: Path, target: Path, mode: str = "rb"):
    """Open ``target`` only if its realpath sits under ``base``'s realpath.

    Re-validates on every call — PLAN.md:245 explicitly forbids treating a
    single check-at-creation as sufficient.
    """
    canonical = safe_realpath_under(base, target)
    fh = open(canonical, mode)
    try:
        yield fh
    finally:
        fh.close()


# --- Project DB path resolution (B4) ----------------------------------------


def validate_db_relpath(path: object) -> Path:
    """Return the canonical on-disk DB path for a user-supplied path string.

    Rules (mirror stack.md "Project paths"):

      * Empty / non-string → ``PathError``.
      * Absolute paths must canonicalize under ``validate_home()``.
      * Relative paths are resolved under ``projects_base()``.
      * The final component must end in ``.db`` — keeps the registry
        self-describing and blocks accidental directory targets.
      * Refuses if any path component is the traversal sentinel ``..``;
        the canonicalize-then-relative-to check below catches the rest.
      * The parent dir is not required to exist (the create-project flow
        will ``mkdir`` it at 0o700).
      * If the final component already exists, it must not be a symlink
        (``lstat``); TOCTOU is re-closed at open time by ``CrawlDB``.
    """
    if not isinstance(path, str):
        raise PathError(f"path must be a string, got {type(path).__name__}")
    raw = path.strip()
    if not raw:
        raise PathError("path is empty")

    raw_path = Path(raw)
    if ".." in raw_path.parts:
        raise PathError(f"path contains traversal segment: {raw!r}")

    if raw_path.is_absolute():
        home = validate_home()
        candidate = raw_path
        try:
            canonical = Path(os.path.realpath(candidate))
            canonical.relative_to(Path(os.path.realpath(home)))
        except (OSError, ValueError):
            raise PathError(
                f"absolute path {raw!r} does not resolve under HOME ({home})"
            ) from None
    else:
        base = projects_base()
        candidate = base / raw_path
        try:
            canonical = Path(os.path.realpath(candidate))
            canonical.relative_to(Path(os.path.realpath(base)))
        except (OSError, ValueError):
            raise PathError(
                f"relative path {raw!r} does not resolve under projects base ({base})"
            ) from None

    if canonical.suffix != ".db":
        raise PathError(f"path must end in .db, got {raw!r}")

    # lstat the user-supplied final component *before* realpath has a chance
    # to resolve a symlink away. The earlier `os.path.realpath(candidate)`
    # call dereferences symlinks, so an `lstat(canonical)` here only sees the
    # link's target and would silently accept a same-base symlink pivot.
    try:
        candidate_lst = os.lstat(candidate)
    except FileNotFoundError:
        candidate_lst = None
    except OSError as exc:
        raise PathError(f"path is not lstatable: {candidate} ({exc})") from None
    if candidate_lst is not None:
        if stat.S_ISLNK(candidate_lst.st_mode):
            raise PathError(f"path is a symlink: {candidate}")
        if not stat.S_ISREG(candidate_lst.st_mode):
            raise PathError(f"path is not a regular file: {candidate}")

    return canonical


# --- Browser path + launcher ------------------------------------------------


def browser_base_paths() -> list[Path]:
    """Return the canonicalized browser-install allowlist for the current OS.

    Hints that do not resolve (e.g. the macOS bundle on a Linux box) are
    simply absent. The launcher will refuse any path that does not have a
    canonical parent in this list.
    """
    out: list[Path] = []
    for hint in _BROWSER_BASE_HINTS:
        try:
            resolved = hint.resolve(strict=False)
        except OSError:
            continue
        out.append(resolved)
    return out


def discover_browser_path() -> Path | None:
    """Return the first canonical Tor Browser executable that validates,
    or ``None`` if none are present on this host.

    Walks ``_BROWSER_EXEC_HINTS`` in order and runs each through
    ``validate_browser_path`` — discovery never relaxes the strict
    posture (lstat, allowlist containment, executable bit). Used by
    ``POST /api/nodes/:id/open`` when ``browser.path`` is unset so a
    default Tor Browser install works without the operator having to
    configure anything. When the change-browser feature ships, this
    helper stays as a fallback for the unconfigured case.
    """
    for candidate in _BROWSER_EXEC_HINTS:
        try:
            return validate_browser_path(str(candidate))
        except PathError:
            continue
    return None


def validate_browser_path(value: object) -> Path:
    """Strict validation of a browser executable path.

    Returns the canonical absolute path on success. Raises ``PathError`` on
    any failure. The check is intentionally paranoid:

      * The final component must not be a symlink (lstat). A symlink whose
        realpath is inside the allowlist still gets rejected — pivot bait.
      * The realpath must sit under one of ``browser_base_paths()``.
      * The path must be a regular file (not a directory, socket, etc.).
      * The file must be executable by the current user.
    """
    if not isinstance(value, str):
        raise PathError(f"browser.path must be a string, got {type(value).__name__}")
    raw = value.strip()
    if not raw:
        raise PathError("browser.path is empty")

    # lstat first so a symlink at the final component is refused outright.
    try:
        lst = os.lstat(raw)
    except OSError as exc:
        raise PathError(f"browser.path does not exist: {raw} ({exc})") from None
    if stat.S_ISLNK(lst.st_mode):
        raise PathError(f"browser.path is a symlink: {raw}")

    try:
        resolved = Path(raw).resolve(strict=True)
    except OSError as exc:
        raise PathError(f"browser.path is not resolvable: {raw} ({exc})") from None

    bases = browser_base_paths()
    for base in bases:
        try:
            resolved.relative_to(base)
            break
        except ValueError:
            continue
    else:
        raise PathError(
            f"browser.path {raw!r} is not inside the allowed install roots "
            f"({', '.join(str(b) for b in bases) or 'none on this OS'})"
        )

    if not resolved.is_file():
        raise PathError(f"browser.path is not a regular file: {resolved}")
    if not os.access(resolved, os.X_OK):
        raise PathError(f"browser.path is not executable: {resolved}")
    return resolved


def _minimal_launch_env() -> dict[str, str]:
    """Strict minimal env for the browser process.

    PATH/LANG/LC_ALL are pinned. DISPLAY is forwarded only if it parses as
    a local X display (``:0``, ``:0.0`` etc.). XAUTHORITY is forwarded only
    if it is a regular file with no symlink at its final component. On
    Wayland systems we also forward ``WAYLAND_DISPLAY`` under the same
    lstat-validated rule (it is the file name of a socket inside
    ``XDG_RUNTIME_DIR``).
    """
    env: dict[str, str] = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
    }

    display = os.environ.get("DISPLAY")
    if display and _DISPLAY_RE.match(display):
        env["DISPLAY"] = display

    xauth = os.environ.get("XAUTHORITY")
    if xauth:
        try:
            lst = os.lstat(xauth)
            if not stat.S_ISLNK(lst.st_mode) and stat.S_ISREG(lst.st_mode):
                env["XAUTHORITY"] = xauth
        except OSError:
            pass

    wayland = os.environ.get("WAYLAND_DISPLAY")
    if wayland and "/" not in wayland and ".." not in wayland:
        env["WAYLAND_DISPLAY"] = wayland
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if runtime and Path(runtime).is_dir():
            env["XDG_RUNTIME_DIR"] = runtime

    return env


def launch_browser(browser_path: str | Path, url: str) -> subprocess.Popen[bytes]:
    """Launch the Tor Browser with ``url``.

    Both arguments are re-validated immediately before exec — even if the
    settings layer validated them moments ago. The URL is forced through
    ``validate_onion_url``; the path is re-run through
    ``validate_browser_path`` (closes the TOCTOU window from PLAN.md:247).

    Returns the ``Popen`` handle. Stdio is detached to ``/dev/null`` and
    the env is restricted; ``shell=False`` (B0 guard would catch any
    regression).
    """
    safe_url = validate_onion_url(url)
    resolved = validate_browser_path(str(browser_path))
    env = _minimal_launch_env()

    # ``--`` forces end-of-options on every browser launcher we support, so
    # the URL can't be re-interpreted as a flag. Path comes first as argv[0].
    return subprocess.Popen(
        [str(resolved), "--", safe_url],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


# --- Sensitive file writes --------------------------------------------------


def write_sensitive_file(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` at mode 0o600 with ``O_NOFOLLOW``.

    ``O_NOFOLLOW`` refuses to follow a symlink at the final component, so
    an attacker can't pre-place ``path`` as a symlink pointing at, say, the
    DB file. A trailing ``chmod(0o600)`` re-asserts the mode in case the
    umask widened it between ``O_CREAT`` and now.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        # Re-assert mode — handles the case where the file already existed
        # at a wider mode.
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as fh:
            fh.write(data)
    finally:
        os.close(fd)


@contextlib.contextmanager
def secure_temp_file(
    suffix: str = "",
    dir: Path | None = None,
) -> Iterator[Path]:
    """Create a 0o600 temp file, yield its path, delete on exit.

    Defaults to placing the temp file under ``projects_base()`` so it
    inherits the analyst's protected tree. Tests and callers that need a
    different location can pass ``dir=``.
    """
    target_dir = dir if dir is not None else projects_base()
    target_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix=suffix, dir=str(target_dir))
    path = Path(name)
    try:
        os.fchmod(fd, 0o600)
        os.close(fd)
        yield path
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


__all__ = [
    "PathError",
    "PROJECT_NAME_RE",
    "validate_home",
    "projects_base",
    "validate_project_name",
    "project_path",
    "create_project_root",
    "safe_realpath_under",
    "open_under",
    "validate_db_relpath",
    "browser_base_paths",
    "validate_browser_path",
    "launch_browser",
    "write_sensitive_file",
    "secure_temp_file",
]
