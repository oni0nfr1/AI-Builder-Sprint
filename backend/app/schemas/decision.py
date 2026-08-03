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

    axis_side: str | None = None
    """이 선택지가 `Decision.value_axis`의 어느 극에 해당하는가. 예: "성장".

    ★[8] 가치관 지도가 성립하는 조건이다.
    라벨은 고민마다 다르다("이직한다" / "대학원 간다" / "사이드를 시작한다").
    라벨을 세면 "1회, 1회, 1회"가 나올 뿐 축을 가로지르는 패턴이 안 보인다.
    같은 축의 같은 극으로 모아야 "성장 4회, 안정 1회"가 된다.
    """


class Decision(BaseModel):
    id: str = Field(default_factory=_uuid)
    user_id: str = "local"
    """누구의 고민인가. 가치 축 재사용도 이 사람 이력 안에서만 일어난다."""

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
