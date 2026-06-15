"""``projects.json`` read/write helpers.

The registry lives at ``projects_base() / "projects.json"`` and is the
backend's source of truth for "what projects exist" and "which one is
active". Writes go through ``security.paths.write_sensitive_file`` so the
file is always 0o600; mutations are atomic via a tempfile + ``os.replace``
so a crash mid-write never lands a half-truncated registry on disk.

The on-disk format is intentionally tiny:

    {"projects": [{"id": "<32-char hex>", "name": "<str>", "path": "<str>"}],
     "active_id": "<id>" | null}

Corrupt or missing files yield an empty registry — the project picker takes
over from there.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ..security.paths import write_sensitive_file


def _empty() -> dict[str, Any]:
    """Fresh empty registry. Returned by load() on missing/malformed files."""
    return {"projects": [], "active_id": None}


# Back-compat alias for callers / tests that import the constant. Treat as
# immutable; every call site that wants a usable copy must go through
# ``_empty()`` (or ``load``), which returns fresh containers each time.
EMPTY: dict[str, Any] = _empty()


def _normalize(data: Any) -> dict[str, Any]:
    """Coerce a parsed JSON blob into the expected shape, dropping junk."""
    if not isinstance(data, dict):
        return _empty()
    projects_in = data.get("projects")
    projects: list[dict[str, Any]] = []
    if isinstance(projects_in, list):
        for entry in projects_in:
            if (
                isinstance(entry, dict)
                and isinstance(entry.get("id"), str)
                and isinstance(entry.get("name"), str)
                and isinstance(entry.get("path"), str)
            ):
                projects.append(
                    {"id": entry["id"], "name": entry["name"], "path": entry["path"]}
                )
    active = data.get("active_id")
    if not isinstance(active, str):
        active = None
    if active is not None and not any(p["id"] == active for p in projects):
        active = None
    return {"projects": projects, "active_id": active}


def load(path: Path) -> dict[str, Any]:
    """Return the parsed registry. Missing or malformed → fresh empty dict."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return _empty()
    except OSError:
        return _empty()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return _empty()
    return _normalize(data)


def save(path: Path, state: dict[str, Any]) -> None:
    """Atomically replace ``path`` with the JSON-serialized ``state``.

    The parent directory is created with 0o700 if missing. The tempfile is
    created in the same directory so ``os.replace`` is an atomic rename
    (cross-device renames are not atomic; this avoids that case).
    """
    normalized = _normalize(state)
    serialized = json.dumps(normalized, indent=2, sort_keys=False).encode("utf-8")

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass

    fd, tmp_name = tempfile.mkstemp(
        prefix=".projects.json.", suffix=".tmp", dir=str(path.parent)
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        write_sensitive_file(tmp_path, serialized)
        os.replace(tmp_path, path)
    except BaseException:
        # Best-effort cleanup of the tempfile if the replace fails.
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


__all__ = ["EMPTY", "load", "save"]
