"""Process-level config loaded from environment variables.

The only knobs here are the ones the app needs to *boot*: port, DB creds,
session secret, first-run admin bootstrap, test-mode flag. Anything that an
admin should be able to tweak at runtime (radio URL, polling cadence, API
keys, alert rules, ...) lives in the Postgres `settings` table instead.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(alias="POSTGRES_DB")
    postgres_host: str = Field(default="db", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    secret_key: str = Field(alias="ADSBUDDY_SECRET_KEY")

    admin_username: str = Field(alias="ADSBUDDY_ADMIN_USERNAME")
    admin_password: str = Field(alias="ADSBUDDY_ADMIN_PASSWORD")

    test_mode: bool = Field(default=False, alias="ADSBUDDY_TEST_MODE")
    # Set by the Pi/tmpfs compose: the database lives in RAM and is wiped on
    # reboot. Drives a warning banner in the UI.
    ephemeral_db: bool = Field(default=False, alias="ADSBUDDY_EPHEMERAL_DB")
    # Optional: pre-configure the adsb-im radio URL from docker-compose. Used
    # only on first boot to seed the "Local radio" source; admins manage it from
    # Admin → Sources afterward. Blank = configure it in the admin UI.
    radio_url: str = Field(default="", alias="ADSBUDDY_RADIO_URL")

    # Access model:
    #   "MultiUser" (default) — guest / user / admin with logins (the full model)
    #   "open" — NO login; every request is treated as the admin. For a trusted
    #            single appliance (e.g. an adsb-im Pi on your tailnet only).
    mode: str = Field(
        default="MultiUser",
        validation_alias=AliasChoices("ADSBUDDY_MODE", "ADSBuddyMode"),
    )

    @property
    def open_mode(self) -> bool:
        return self.mode.strip().lower() == "open"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """Alembic uses a sync driver (psycopg v3)."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
