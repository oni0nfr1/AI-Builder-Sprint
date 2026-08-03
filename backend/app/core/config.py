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
    upstage_embedding_model: str = "embedding-query"
    """[3] 잠재 축 — 발화 내용의 의미 벡터 (4096차원)."""

    # 서버측 STT — 브라우저 Web Speech 는 구글 서버에 의존해 환경마다 실패한다 (Q7)
    stt_enabled: bool = True
    whisper_model: str = "base"
    """tiny(~75MB) | base(~145MB) | small(~480MB). 클수록 한국어 품질이 오르고 느려진다."""

    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    """CPU 에서는 int8 이 가장 빠르다. GPU 를 쓴다면 float16."""

    cors_origins: str = "http://localhost:5173"
    db_path: str = "./intuition.db"

    # 개발 전용 rPPG A/B 진단. RGB 시계열을 받는 비저장 엔드포인트를 여는 스위치다.
    # 프로덕션에서 실수로 원자료 수집 경로를 열지 않도록 기본값은 반드시 false다.
    rppg_diagnostics_enabled: bool = False

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
