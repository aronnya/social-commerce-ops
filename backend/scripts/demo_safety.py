"""Safety checks for synthetic demo seeding.

Stdlib only: tests can import this without a database or application settings.
The functions never return or print passwords.
"""

from __future__ import annotations

from urllib.parse import urlparse

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SAFE_DB_NAME_TOKENS = ("demo", "test")


class UnsafeDemoTargetError(RuntimeError):
    """Raised when demo seeding is not allowed for the configured database."""


def _public_url_for_parse(url: str) -> str:
    trimmed = url.strip()
    for prefix, replacement in (
        ("postgresql+psycopg://", "postgresql://"),
        ("postgres://", "postgresql://"),
    ):
        if trimmed.startswith(prefix):
            return replacement + trimmed[len(prefix) :]
    return trimmed


def database_target(url: str) -> tuple[str, str]:
    """Return (hostname, database_name). Password is not included."""
    parsed = urlparse(_public_url_for_parse(url))
    host = (parsed.hostname or "").lower()
    name = (parsed.path or "").lstrip("/").split("/")[0].lower()
    return host, name


def is_safe_demo_database_url(url: str | None) -> bool:
    if not url or not str(url).strip():
        return False
    host, name = database_target(url)
    if host not in LOOPBACK_HOSTS:
        return False
    return any(token in name for token in SAFE_DB_NAME_TOKENS)


def assert_demo_seed_allowed(*, allow_flag: str | None, database_url: str | None) -> None:
    if (allow_flag or "").strip() != "1":
        raise UnsafeDemoTargetError(
            "Refusing to seed: set ALLOW_DEMO_SEED=1 for a local demo/test database."
        )
    if not database_url or not str(database_url).strip():
        raise UnsafeDemoTargetError(
            "Refusing to seed: no demo/test database URL is configured."
        )
    if not is_safe_demo_database_url(database_url):
        raise UnsafeDemoTargetError(
            "Refusing to seed: the database is not a loopback host whose name "
            "contains 'demo' or 'test'."
        )
