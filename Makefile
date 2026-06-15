# Onion Rabbithole — top-level Makefile
#
# Targets:
#   setup           one-time bootstrap (venv, pip, npm)
#   lint-security   B0 security guards (build-blocking)
#   test            lint-security + pytest
#   dev             run backend + frontend dev servers
#   dev-backend     run FastAPI on :7654
#   dev-frontend    run Vite on :5173
#   build           production frontend build -> backend/public/

.PHONY: setup lint-security test dev dev-backend dev-frontend build clean

PY     := backend/.venv/bin/python
PIP    := backend/.venv/bin/pip
PYTEST := backend/.venv/bin/pytest

setup:
	bash scripts/bootstrap.sh

# Phase B0 — build-blocking grep guards.
# Each rule returns zero results in a clean tree; the rule fails the build if any match appears.
# `grep ... || true` swallows "directory does not exist" so this works pre-B1.
# `--exclude-dir` skips the venv, build caches, and __pycache__ so vendored deps aren't scanned.
PY_EXCL := --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=.pytest_cache --exclude-dir=.mypy_cache --exclude-dir=.ruff_cache
JS_EXCL := --exclude-dir=node_modules --exclude-dir=dist
lint-security:
	@echo ">> lint-security"
	@hits=$$(grep -rn $(PY_EXCL) 'aiohttp\.ClientSession(' backend/backend/ --include='*.py' 2>/dev/null | grep -v 'security/net.py' || true); \
	  if [ -n "$$hits" ]; then echo "FAIL: aiohttp.ClientSession() outside security/net.py:"; echo "$$hits"; exit 1; fi
	@hits=$$(grep -rn $(JS_EXCL) '{@html' frontend/src/ 2>/dev/null || true); \
	  if [ -n "$$hits" ]; then echo "FAIL: {@html} in frontend:"; echo "$$hits"; exit 1; fi
	@hits=$$(grep -rnE $(PY_EXCL) 'ssl=False|verify=False' backend/ --include='*.py' 2>/dev/null || true); \
	  if [ -n "$$hits" ]; then echo "FAIL: ssl=False / verify=False in backend:"; echo "$$hits"; exit 1; fi
	@hits=$$(grep -rn $(PY_EXCL) 'shell=True' backend/ --include='*.py' 2>/dev/null || true); \
	  if [ -n "$$hits" ]; then echo "FAIL: shell=True in backend:"; echo "$$hits"; exit 1; fi
	@hits=$$(grep -rn $(PY_EXCL) 'socket\.getaddrinfo' backend/backend/ --include='*.py' 2>/dev/null || true); \
	  if [ -n "$$hits" ]; then echo "FAIL: socket.getaddrinfo in backend:"; echo "$$hits"; exit 1; fi
	@hits=$$(grep -rn $(PY_EXCL) '\._conn' backend/backend/ --include='*.py' 2>/dev/null | grep -v 'backend/backend/db/core.py' || true); \
	  if [ -n "$$hits" ]; then echo "FAIL: raw DB connection access (._conn) outside db/core.py — use db.read() or db.transaction():"; echo "$$hits"; exit 1; fi
	@echo "OK"

test: lint-security
	@test -x $(PYTEST) || { echo "venv not set up — run 'make setup'"; exit 1; }
	cd backend && .venv/bin/pytest

dev:
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	@test -x $(PY) || { echo "venv not set up — run 'make setup'"; exit 1; }
	cd backend && .venv/bin/python -m backend

dev-frontend:
	cd frontend && npm run dev

# Single-bundle build guard: exactly one bundle.js and one bundle.css at the top of backend/public/.
build:
	cd frontend && npm run build
	@test -f backend/public/bundle.js || { echo "FAIL: backend/public/bundle.js missing"; exit 1; }
	@test -f backend/public/bundle.css || { echo "FAIL: backend/public/bundle.css missing"; exit 1; }
	@count=$$(find backend/public -maxdepth 1 -type f \( -name '*.js' -o -name '*.css' \) | wc -l | tr -d ' '); \
	  if [ "$$count" != "2" ]; then \
	    echo "FAIL: expected exactly bundle.js + bundle.css at top of backend/public/, found $$count:"; \
	    find backend/public -maxdepth 1 -type f \( -name '*.js' -o -name '*.css' \); \
	    exit 1; \
	  fi
	@echo "OK"

clean:
	rm -rf backend/.venv frontend/node_modules backend/public/bundle.js backend/public/bundle.css backend/public/assets
