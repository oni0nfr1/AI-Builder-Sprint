"""[7] 저장 + [8] 축적 — Session / Retrospective / ValueMap."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.analysis import Delta, Verdict
from app.schemas.capture import Capture
from app.schemas.features import Features
from app.schemas.report import Annotation, Report


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Session(BaseModel):
    id: str = Field(default_factory=_uuid)
    decision_id: str
    captures: list[Capture] = Field(default_factory=list)
    features: list[Features] = Field(default_factory=list)
    delta: Delta | None = None

    verdict: Verdict | None = None
    """내부 판정. 사용자에게 직접 노출하지 않는다."""

    report: Report | None = None
    annotation: Annotation | None = None
    created_at: datetime = Field(default_factory=_now)


class Horizon(StrEnum):
    W1 = "1w"
    """1주. 3개월을 기다리지 않고 첫 피드백 루프를 돌린다."""

    M3 = "3m"
    M6 = "6m"
    Y1 = "1y"


class Retrospective(BaseModel):
    """시간차 회고. 확신(3층)의 재료."""

    session_id: str
    horizon: Horizon
    chosen_option_id: str | None = None
    """실제로 무엇을 골랐나."""

    satisfaction: int = Field(ge=1, le=5)
    note: str | None = None
    created_at: datetime = Field(default_factory=_now)


class ValueAxisEntry(BaseModel):
    axis: str
    session_ids: list[str] = Field(default_factory=list)
    lean_pattern: str = ""
    """이 축에서 반복적으로 어느 쪽으로 기울었는가."""


class ValueMap(BaseModel):
    """가치관 지도 (2층). `Decision.value_axis`를 가로질러 집계한다.

    축 추출 방식은 OPEN_QUESTIONS Q5 참조 — 아직 열린 질문이다.
    """

    axes: list[ValueAxisEntry] = Field(default_factory=list)


class ConvictionGroup(BaseModel):
    """자기 진술대로 골랐는가로 나눈 한 무리."""

    followed_intuition: bool
    count: int = 0
    average_satisfaction: float | None = None


class Conviction(BaseModel):
    """확신 (3층). "내 직관은 믿을 만한가"의 재료.

    ★결론을 내지 않는다. 자기 진술(`annotation.self_lean_option_id`)대로 고른 경우와
    그러지 않은 경우의 만족도를 나란히 놓을 뿐이고, 그 대조에서 무엇을 읽을지는
    사용자가 정한다. "당신의 직관은 정확합니다"는 결정 대행이다.

    비교 대상이 우리 판정(`verdict.lean`)이 아니라 **사용자가 자기 입으로 말한 것**인
    이유도 같다 — 자기가 말한 것만이 자기 기준점이 된다.
    """

    total_retrospectives: int = 0
    groups: list[ConvictionGroup] = Field(default_factory=list)
    note: str = ""
    """관찰 한 문장. 판정이 아니다."""
