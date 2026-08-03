"""[1] 캡처 — 브라우저에서 올라오는 원자료.

프라이버시 전제: 영상 프레임 원본은 서버로 보내지 않는다.
새 흐름은 rppg-web이 브라우저에서 계산한 심박/품질 요약만 전송한다.
기존 RGB 시계열은 호환 경로로만 받는다.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())


class Segment(StrEnum):
    NEUTRAL = "neutral"
    """중립 앵커. default 확보 + rPPG 워밍업. 고민과 무관한 발화여야 한다."""

    OPTION = "option"


class Phase(StrEnum):
    IMAGINE = "imagine"
    """상상 구간(정지). 심박 측정. 말하면 얼굴 근육이 움직여 rPPG가 깨지므로 여기서 잰다."""

    SPEAK = "speak"
    """발화 구간. 음성 측정."""


class RgbSample(BaseModel):
    t: float
    """시작 기준 경과 초."""

    r: float
    g: float
    b: float


class RppgMeasurement(BaseModel):
    """브라우저 안에서 rppg-web으로 계산한 요약값."""

    source: Literal["rppg-web"]
    version: str
    bpm: float = Field(gt=0.0)
    confidence: float = Field(ge=0.0, le=1.0)
    signal_quality: float = Field(ge=0.0, le=1.0)
    agreement: float | None = Field(default=None, ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)
    stable_sample_count: int = Field(ge=1)


class Capture(BaseModel):
    id: str = Field(default_factory=_uuid)
    session_id: str
    segment: Segment
    option_id: str | None = None
    """segment == OPTION 일 때만 채워진다."""

    phase: Phase

    rgb_series: list[RgbSample] | None = None
    """레거시 서버 분석 경로. rppg_measurement가 없을 때만 사용."""

    rppg_measurement: RppgMeasurement | None = None
    """새 클라이언트 분석 경로. 영상/RGB 원자료를 포함하지 않는다."""

    audio_base64: str | None = None
    """phase == SPEAK 에서 필수."""

    transcript: str | None = None
    """브라우저 STT 결과."""

    fps: float = 0.0
    """rgb_series 실측 프레임레이트. rPPG 주파수 해석에 필요."""

    duration_sec: float = 0.0
