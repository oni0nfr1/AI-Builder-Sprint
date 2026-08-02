"""[0] 고민 등록."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core import storage
from app.core.identity import current_user
from app.schemas import ApiResponse, Decision, DecisionCreateRequest
from app.services import decision_service

router = APIRouter(prefix="/decisions", tags=["decisions"])


@router.post("", response_model=ApiResponse[Decision])
async def create_decision(
    req: DecisionCreateRequest, user_id: str = Depends(current_user)
) -> ApiResponse[Decision]:
    """고민 한 문장 → 선택지 + 가치축 + 상상/발화 프롬프트 추출.

    두 선택지의 프롬프트는 구조적으로 대칭이어야 한다 — 어느 쪽을 권하는
    뉘앙스가 섞이면 [5] 리포트 이전에 이미 유도가 일어난다.
    """
    decision = await decision_service.parse_decision(req.raw_input, user_id)
    decision.user_id = user_id
    storage.put(
        "decisions", decision.id, decision.model_dump(mode="json"), user_id=user_id
    )
    return ApiResponse.success(decision)


@router.get("/{decision_id}", response_model=ApiResponse[Decision])
async def get_decision(decision_id: str) -> ApiResponse[Decision]:
    raw = storage.get("decisions", decision_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="고민을 찾을 수 없습니다.")
    return ApiResponse.success(Decision.model_validate(raw))
