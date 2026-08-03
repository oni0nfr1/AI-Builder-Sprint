"""개발 전용 rPPG 비교 계약.

프로덕션 Capture 계약과 의도적으로 분리한다. 이 요청의 RGB 시계열은 기존 CHROM
결과를 즉시 계산하는 데만 쓰이며 저장하지 않는다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.schemas.capture import RgbSample, RppgMeasurement
from app.schemas.features import HeartRateFeatures


class RppgComparisonRequest(BaseModel):
    rgb_series: list[RgbSample] | None = Field(default=None, min_length=64, max_length=3600)
    fps: float = Field(default=0.0, ge=0.0, le=120.0)
    duration_sec: float = Field(ge=4.0, le=60.0)
    rppg_web: RppgMeasurement | None = None
    reference_bpm: float | None = Field(default=None, ge=30.0, le=240.0)

    @model_validator(mode="after")
    def require_measurement_input(self) -> "RppgComparisonRequest":
        if self.rgb_series is None and self.rppg_web is None:
            raise ValueError("rgb_series 또는 rppg_web 중 하나는 필요합니다.")
        if self.rgb_series is not None and self.fps <= 1.0:
            raise ValueError("rgb_series가 있으면 fps는 1보다 커야 합니다.")
        return self


class RppgComparisonResult(BaseModel):
    server_chrom: HeartRateFeatures | None
    rppg_web: RppgMeasurement | None
    reference_bpm: float | None
    server_absolute_error: float | None
    web_absolute_error: float | None
    bpm_difference: float | None
