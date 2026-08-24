from functools import lru_cache
import json

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:///./milyzebra.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "development-only-change-me"
    jwt_issuer: str = "mily-zebra"
    jwt_ttl_minutes: int = 480
    bootstrap_token: str = Field(
        default="",
        validation_alias=AliasChoices("MZ_BOOTSTRAP_TOKEN", "BOOTSTRAP_TOKEN"),
    )
    certified_external_modules: str = Field(
        default="",
        validation_alias=AliasChoices(
            "MZ_CERTIFIED_EXTERNAL_MODULES",
            "CERTIFIED_EXTERNAL_MODULES",
        ),
    )
    sandbox_external_modules: str = Field(
        default="",
        validation_alias=AliasChoices(
            "MZ_SANDBOX_EXTERNAL_MODULES",
            "SANDBOX_EXTERNAL_MODULES",
        ),
    )
    payment_sandbox_webhook_secret: str = Field(
        default="mily-zebra-sandbox-only",
        validation_alias=AliasChoices(
            "MZ_PAYMENT_SANDBOX_WEBHOOK_SECRET",
            "PAYMENT_SANDBOX_WEBHOOK_SECRET",
        ),
    )
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    auto_create_schema: bool = True
    media_root: str = "/data/media"
    max_image_bytes: int = 10 * 1024 * 1024
    ollama_url: str = ""
    ollama_model: str = "qwen3:1.7b"
    ai_timeout_seconds: int = 45
    worker_poll_seconds: float = 2.0
    outbox_targets_json: str = "{}"
    outbox_hmac_secret: str = ""
    outbox_timeout_seconds: int = 15

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @staticmethod
    def _module_set(value: str) -> frozenset[str]:
        return frozenset(
            item.strip().lower()
            for item in value.split(",")
            if item.strip()
        )

    @property
    def certified_external_module_set(self) -> frozenset[str]:
        return self._module_set(self.certified_external_modules)

    @property
    def sandbox_external_module_set(self) -> frozenset[str]:
        return self._module_set(self.sandbox_external_modules)

    @property
    def outbox_targets(self) -> dict[str, str]:
        try:
            value = json.loads(self.outbox_targets_json or "{}")
        except json.JSONDecodeError:
            return {}
        if not isinstance(value, dict):
            return {}
        return {
            str(key): str(url).strip()
            for key, url in value.items()
            if str(key).strip() and str(url).strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
