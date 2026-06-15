# PREFLIGHT

This file lists the system-level prerequisites for running Onion Rabbithole on a
machine. Use it before `make setup`.

For day-to-day commands after the machine is ready, see
`docs/reference/runbook.md`.

## Required System Tools

| Tool | Minimum | Verify |
| --- | --- | --- |
| Python | 3.12 or newer | `python3 --version` |
| SQLite library | 3.41+ with FTS5 and loadable extensions | see SQLite check below |
| Node.js | 20.x LTS or newer | `node --version` |
| npm | bundled with Node.js | `npm --version` |
| git | modern git | `git --version` |
| make | modern make | `make --version` |
| Tor | SOCKS proxy on loopback | `ss -tlnp \| grep 9050` |

Optional:

| Tool | Used For | Verify |
| --- | --- | --- |
| Ollama | Local LLM analyses | `curl -s 127.0.0.1:11434/api/version` |

## Package Install Examples

Arch:

```sh
sudo pacman -S --needed python sqlite nodejs npm git make tor
sudo systemctl enable --now tor
```

Debian, Ubuntu, or Parrot:

```sh
sudo apt install -y python3 python3-venv python3-pip sqlite3 libsqlite3-0 nodejs npm git make tor
sudo systemctl enable --now tor
```

Other distributions should install equivalent packages. Ensure Python's SQLite
module links against a SQLite build with FTS5 and loadable extension support.

## SQLite Capability Check

Run:

```sh
python3 - <<'PY'
import sqlite3
c = sqlite3.connect(":memory:")
print("version:", sqlite3.sqlite_version)
try:
    c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
    print("fts5: yes")
except sqlite3.OperationalError as e:
    print("fts5: NO -", e)
print("load_extension:", hasattr(c, "enable_load_extension"))
PY
```

Required:

- SQLite version `3.41` or newer
- `fts5: yes`
- `load_extension: True`

If `load_extension` is false, `sqlite-vec` cannot load. Use a Python build that
links against a fuller SQLite library.

## Tor

The default project setting expects Tor at:

```text
socks5h://127.0.0.1:9050
```

Verify the port is listening:

```sh
ss -tlnp | grep 9050
```

The backend requires a loopback `socks5h` proxy so onion hostname resolution
happens through Tor.

## Optional Ollama

LLM analysis workflows expect a loopback Ollama endpoint by default:

```text
http://127.0.0.1:11434
```

Verify:

```sh
curl -s 127.0.0.1:11434/api/version
```

Non-loopback Ollama URLs are rejected by the backend security model.

## Bootstrap After Preflight

Once the machine has the required tools:

```sh
make setup
```

`make setup` runs `scripts/bootstrap.sh`, which:

1. selects Python 3.12+,
2. creates `backend/.venv`,
3. installs backend runtime and dev requirements,
4. installs frontend npm dependencies,
5. sanity-checks SQLite FTS5 and loadable-extension support.

Then verify the security guardrails:

```sh
make lint-security
```

For running the app, building assets, and running tests, use
`docs/reference/runbook.md`.

## Common Preflight Failures

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `Python 3.12+ required` | Older Python on `PATH` | Install Python 3.12+ or adjust `PATH`. |
| `fts5: NO` | SQLite built without FTS5 | Install a fuller distro SQLite package or use another Python build. |
| `load_extension: False` | Python SQLite lacks loadable extension support | Use a Python build linked against SQLite with loadable extensions. |
| `sqlite-vec` install or import fails | Loadable extensions unavailable | Fix Python/SQLite linkage. |
| `fastembed` install is slow or large | ONNX Runtime/model dependencies | Expected on first install. |
| Tor port `9050` not listening | Tor service not running | Start Tor or update the project `tor.proxy` setting to the correct loopback SOCKS port. |
| `make lint-security` fails | A guardrail found unsafe code | Read the failing rule output and fix the named file. |
