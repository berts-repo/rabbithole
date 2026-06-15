#!/usr/bin/env bash
# Onion Rabbithole — idempotent bootstrap.
# Creates the directory shells, the Python venv, and installs deps if requirements files exist.
# Safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo ">> bootstrap @ $ROOT"

# --- Python check ---------------------------------------------------------
# Requires Python 3.12 or newer. Prefer an explicit `python3.12` binary, else
# fall back to `python3` if its version is >= 3.12.
pick_python() {
  for candidate in python3.12 python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}
PY=$(pick_python) || {
  echo "ERROR: Python 3.12+ required. See PREFLIGHT.md." >&2
  exit 1
}
echo "   python: $($PY --version)"

# --- Directory shells -----------------------------------------------------
mkdir -p backend/backend/db backend/backend/crawler backend/backend/routes \
         backend/backend/services backend/backend/security backend/backend/export \
         backend/public backend/tests \
         frontend/src/lib/stores frontend/src/components frontend/src/views \
         scripts

# Public dir needs a .gitkeep so the empty dir survives in git pre-build.
[ -f backend/public/.gitkeep ] || touch backend/public/.gitkeep

# --- Venv -----------------------------------------------------------------
if [ ! -d backend/.venv ]; then
  echo "   creating venv at backend/.venv"
  $PY -m venv backend/.venv
fi
# shellcheck disable=SC1091
source backend/.venv/bin/activate
pip install --upgrade pip >/dev/null

if [ -f backend/requirements.txt ]; then
  echo "   pip install -r backend/requirements.txt"
  pip install -r backend/requirements.txt
fi
if [ -f backend/requirements-dev.txt ]; then
  echo "   pip install -r backend/requirements-dev.txt"
  pip install -r backend/requirements-dev.txt
fi

# --- Frontend node deps (only if package.json already exists) ------------
if [ -f frontend/package.json ]; then
  echo "   npm install (frontend)"
  (cd frontend && npm install)
else
  echo "   frontend/package.json not present yet — skipping npm install"
fi

# --- Sanity check ---------------------------------------------------------
echo ">> sanity: SQLite features"
$PY - <<'PY'
import sqlite3, sys
conn = sqlite3.connect(":memory:")
have_fts5 = False
try:
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    have_fts5 = True
except sqlite3.OperationalError:
    pass
have_load_ext = hasattr(conn, "enable_load_extension")
print(f"   sqlite: {sqlite3.sqlite_version}  fts5={have_fts5}  loadable_extensions={have_load_ext}")
if not have_fts5:
    print("   WARN: FTS5 missing — keyword search will not work. See PREFLIGHT.md.", file=sys.stderr)
if not have_load_ext:
    print("   WARN: sqlite was built without loadable extensions — sqlite-vec will fail. See PREFLIGHT.md.", file=sys.stderr)
PY

echo ">> done"
