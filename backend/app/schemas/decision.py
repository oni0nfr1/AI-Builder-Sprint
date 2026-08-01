"""[0] 고민 등록 — Decision / Option."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Option(BaseModel):
    """고민의 선택지 하나.

    `imagine_prompt`/`speak_prompt`는 LLM이 생성하되, 어느 쪽을 권하는
    뉘앙스가 섞이면 안 된다. 두 선택지의 프롬프트는 구조적으로 대칭이어야 한다.
    """

    id: str = Field(default_factory=_uuid)
    label: str
    imagine_prompt: str
    speak_prompt: str
    order_index: int = 0
    """실제 제시 순서. 순서 효과 보정을 위해 랜덤화 결과를 기록한다 (OPEN_QUESTIONS Q1)."""


class Decision(BaseModel):
    id: str = Field(default_factory=_uuid)
    raw_input: str
    """사용자가 말하거나 쓴 원문."""

    title: str
    """LLM이 정규화한 제목. 예: "이직할지 말지"."""

    value_axis: str
    """LLM이 추출한 가치 축. 예: "안정 vs 성장". [8] 가치관 지도의 축이 된다."""

    options: list[Option]
    created_at: datetime = Field(default_factory=_now)


class DecisionCreateRequest(BaseModel):
    raw_input: str
