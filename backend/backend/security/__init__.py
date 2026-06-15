"""Security primitives — auth (B1), paths (B3), net (B3)."""
from .auth import ApiAuthMiddleware, COOKIE_NAME, EXPECTED_ORIGIN, SessionState, new_session, verify_origin, verify_token  # noqa: F401
from .net import (  # noqa: F401
    ConfigError,
    DEFAULT_TIMEOUT,
    EgressError,
    LOOPBACK_HOSTS,
    MAX_RESPONSE_BYTES,
    ONION_HOST_RE,
    ONION_URL_RE,
    TOR_PROXY_RE,
    is_loopback_host,
    make_tor_session,
    validate_onion_host,
    validate_onion_url,
    validate_tor_proxy,
)
from .paths import (  # noqa: F401
    PROJECT_NAME_RE,
    PathError,
    browser_base_paths,
    create_project_root,
    launch_browser,
    open_under,
    project_path,
    projects_base,
    safe_realpath_under,
    secure_temp_file,
    validate_browser_path,
    validate_home,
    validate_project_name,
    write_sensitive_file,
)
