"""[1] 캡처 — 브라우저에서 올라오는 원자료.

프라이버시 전제: 영상 프레임 원본은 서버로 보내지 않는다.
브라우저에서 MediaPipe로 얼굴 ROI를 잡고 RGB 평균 숫자만 전송한다.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

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


class Capture(BaseModel):
    id: str = Field(default_factory=_uuid)
    session_id: str
    segment: Segment
    option_id: str | None = None
    """segment == OPTION 일 때만 채워진다."""

    phase: Phase

    rgb_series: list[RgbSample] | None = None
    """phase == IMAGINE 에서 필수."""

    audio_base64: str | None = None
    """phase == SPEAK 에서 필수."""

    transcript: str | None = None
    """브라우저 STT 결과."""

    fps: float = 0.0
    """rgb_series 실측 프레임레이트. rPPG 주파수 해석에 필요."""

    duration_sec: float = 0.0
