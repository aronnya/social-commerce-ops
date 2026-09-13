from urllib.parse import quote_plus

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Make a Postgres URL safe for SQLAlchemy + psycopg.

    Accepts postgresql:// or postgres:// so the .env file can keep the
    string the host provided. Special characters in the password are
    percent-encoded in memory; the original .env value is not rewritten.
    """
    trimmed = url.strip()
    if not trimmed:
        return trimmed

    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if trimmed.startswith(prefix):
            rest = trimmed[len(prefix) :]
            break
    else:
        return trimmed

    at_index = rest.rfind("@")
    if at_index == -1:
        normalized = f"postgresql+psycopg://{rest}"
    else:
        userinfo, host_part = rest[:at_index], rest[at_index + 1 :]
        username, separator, password = userinfo.partition(":")
        if separator:
            userinfo = f"{username}:{quote_plus(password)}"
        normalized = f"postgresql+psycopg://{userinfo}@{host_part}"

    host_and_path = normalized.split("@", 1)[-1]
    hostname = host_and_path.split("/", 1)[0].split(":", 1)[0].lower()
    local = hostname in {"localhost", "127.0.0.1", "::1"}
    if not local and "sslmode=" not in normalized:
        joiner = "&" if "?" in normalized else "?"
        normalized = f"{normalized}{joiner}sslmode=require"

    return normalized


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Social Commerce Operations Platform"
    database_url: str | None = None
    test_database_url: str | None = None
    cors_origins: str = "http://localhost:5173"

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def _normalize_urls(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return normalize_database_url(text)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
