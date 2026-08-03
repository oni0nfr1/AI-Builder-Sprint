"""공통 타입 — 지표 키와 API 응답 래퍼.

계약 정의는 `docs/CONTRACTS.md` 참조.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class MetricKey(StrEnum):
    """Delta 계산에 쓰이는 표준 지표 키.

    모든 파이프라인 단계가 같은 이름을 쓴다. 새 지표를 추가할 때는
    `docs/CONTRACTS.md`의 표도 함께 갱신할 것.
    """

    F0_MEAN = "f0_mean"
    F0_STD = "f0_std"
    LOUDNESS_MEAN = "loudness_mean"
    JITTER_LOCAL = "jitter_local"
    SHIMMER_LOCAL = "shimmer_local"
    HNR = "hnr"
    SPEECH_RATE = "speech_rate"
    PAUSE_RATIO = "pause_ratio"
    BPM = "bpm"


VOICE_METRICS: tuple[MetricKey, ...] = (
    MetricKey.F0_MEAN,
    MetricKey.F0_STD,
    MetricKey.LOUDNESS_MEAN,
    MetricKey.JITTER_LOCAL,
    MetricKey.SHIMMER_LOCAL,
    MetricKey.HNR,
    MetricKey.SPEECH_RATE,
    MetricKey.PAUSE_RATIO,
)

HR_METRICS: tuple[MetricKey, ...] = (MetricKey.BPM,)


class ApiError(BaseModel):
    code: str
    message: str


class ApiResponse(BaseModel, Generic[T]):
    """팀 컨벤션 응답 형식: {ok, data, error}."""

    ok: bool = True
    data: T | None = None
    error: ApiError | None = None

    @classmethod
    def success(cls, data: T) -> "ApiResponse[T]":
        return cls(ok=True, data=data, error=None)

    @classmethod
    def failure(cls, code: str, message: str) -> "ApiResponse[Any]":
        return cls(ok=False, data=None, error=ApiError(code=code, message=message))


class MetricDelta(BaseModel):
    """지표별 상대 변화율. 절대치는 쓰지 않는다.

    값은 비율(ratio): 0.18 == 18% 높음, -0.12 == 12% 낮음.
    """

    values: dict[MetricKey, float] = Field(default_factory=dict)

    def get(self, key: MetricKey) -> float | None:
        return self.values.get(key)
