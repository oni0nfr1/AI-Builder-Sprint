"""환경 설정. API 키는 .env 에만 — 코드에 하드코딩하거나 커밋하지 않는다."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Upstage Solar — [0] 고민 파싱, [5] 메타인지 리포트
    upstage_api_key: str = ""
    upstage_base_url: str = "https://api.upstage.ai/v1"
    upstage_model: str = "solar-pro2"

    cors_origins: str = "http://localhost:5173"
    db_path: str = "./intuition.db"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_enabled(self) -> bool:
        """키가 없으면 LLM 단계는 규칙 기반 폴백으로 동작한다."""
        return bool(self.upstage_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
