"""[2] 특징 추출 — Features."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import MetricKey


class VoiceFeatures(BaseModel):
    f0_mean: float
    f0_std: float
    loudness_mean: float
    jitter_local: float
    shimmer_local: float
    hnr: float
    speech_rate: float
    pause_ratio: float

    egemaps: dict[str, float] | None = None
    """eGeMAPS 88 전체. openSMILE이 있을 때만 채워진다."""

    def as_metrics(self) -> dict[MetricKey, float]:
        return {
            MetricKey.F0_MEAN: self.f0_mean,
            MetricKey.F0_STD: self.f0_std,
            MetricKey.LOUDNESS_MEAN: self.loudness_mean,
            MetricKey.JITTER_LOCAL: self.jitter_local,
            MetricKey.SHIMMER_LOCAL: self.shimmer_local,
            MetricKey.HNR: self.hnr,
            MetricKey.SPEECH_RATE: self.speech_rate,
            MetricKey.PAUSE_RATIO: self.pause_ratio,
        }


class HeartRateFeatures(BaseModel):
    bpm: float
    confidence: float = Field(ge=0.0, le=1.0)
    """0~1. 항상 반환한다 — 웹캠 rPPG는 조명·움직임에 민감하다.

    CONFIDENCE_FLOOR 미만이면 [4] 판정에서 심박 축을 제외하고 음성만으로 간다.
    """

    snr_db: float = 0.0

    hrv_rmssd: float | None = None
    """MVP(웹캠 rPPG)에서는 항상 None. 웨어러블 연동 시 채운다."""

    def as_metrics(self) -> dict[MetricKey, float]:
        return {MetricKey.BPM: self.bpm}


CONFIDENCE_FLOOR = 0.4
"""이 값 미만의 rPPG 신뢰도는 판정에서 제외한다."""


class Features(BaseModel):
    capture_id: str
    voice: VoiceFeatures | None = None
    """phase == SPEAK 에서만."""

    hr: HeartRateFeatures | None = None
    """phase == IMAGINE 에서만."""

    def as_metrics(self) -> dict[MetricKey, float]:
        metrics: dict[MetricKey, float] = {}
        if self.voice is not None:
            metrics.update(self.voice.as_metrics())
        if self.hr is not None and self.hr.confidence >= CONFIDENCE_FLOOR:
            metrics.update(self.hr.as_metrics())
        return metrics
