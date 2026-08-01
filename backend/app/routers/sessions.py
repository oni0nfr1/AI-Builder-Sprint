"""[1]~[8] 세션 파이프라인."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import storage
from app.schemas import (
    Annotation,
    ApiResponse,
    Capture,
    Decision,
    Features,
    Report,
    Retrospective,
    Session,
    ValueMap,
)
from app.services import analysis_service, feature_service, report_service, value_map_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreateRequest(BaseModel):
    decision_id: str


def _load_session(session_id: str) -> Session:
    raw = storage.get("sessions", session_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return Session.model_validate(raw)


def _save_session(session: Session) -> None:
    storage.put(
        "sessions",
        session.id,
        session.model_dump(mode="json"),
        decision_id=session.decision_id,
    )


@router.post("", response_model=ApiResponse[Session])
async def create_session(req: SessionCreateRequest) -> ApiResponse[Session]:
    if storage.get("decisions", req.decision_id) is None:
        raise HTTPException(status_code=404, detail="고민을 찾을 수 없습니다.")
    session = Session(decision_id=req.decision_id)
    _save_session(session)
    return ApiResponse.success(session)


@router.post("/{session_id}/captures", response_model=ApiResponse[Features])
async def upload_capture(session_id: str, capture: Capture) -> ApiResponse[Features]:
    """[1] 캡처 수신 → [2] 특징 추출 즉시 실행.

    영상 원본은 받지 않는다. 브라우저가 얼굴 ROI의 RGB 평균 시계열만 보낸다.
    """
    session = _load_session(session_id)
    capture.session_id = session_id

    features = feature_service.extract(capture)

    session.captures.append(capture)
    session.features.append(features)
    _save_session(session)
    return ApiResponse.success(features)


@router.post("/{session_id}/analyze", response_model=ApiResponse[Report])
async def analyze(session_id: str) -> ApiResponse[Report]:
    """[3] 상대화 → [4] 판정 → [5] 리포트.

    반환하는 것은 Report 뿐이다. Verdict(내부 판정)는 세션에 저장만 하고
    클라이언트로 보내지 않는다 — 우리가 판정했다는 사실이 노출되면
    사용자는 다시 결정을 아웃소싱하게 된다.
    """
    session = _load_session(session_id)
    raw_decision = storage.get("decisions", session.decision_id)
    if raw_decision is None:
        raise HTTPException(status_code=404, detail="고민을 찾을 수 없습니다.")
    decision = Decision.model_validate(raw_decision)

    delta = analysis_service.compute_delta(session, decision)
    verdict = analysis_service.judge(delta, decision)
    report = await report_service.build_report(verdict, delta, decision, session)

    session.delta = delta
    session.verdict = verdict
    session.report = report
    _save_session(session)
    return ApiResponse.success(report)


@router.post("/{session_id}/annotation", response_model=ApiResponse[Annotation])
async def save_annotation(
    session_id: str, annotation: Annotation
) -> ApiResponse[Annotation]:
    """[6] 사용자 태깅. self_lean_option_id 가 이 제품의 핵심 산출물이다."""
    session = _load_session(session_id)
    annotation.session_id = session_id
    session.annotation = annotation
    _save_session(session)
    return ApiResponse.success(annotation)


@router.get("/{session_id}", response_model=ApiResponse[Session])
async def get_session(session_id: str) -> ApiResponse[Session]:
    return ApiResponse.success(_load_session(session_id))


@router.post("/{session_id}/retrospective", response_model=ApiResponse[Retrospective])
async def save_retrospective(
    session_id: str, retro: Retrospective
) -> ApiResponse[Retrospective]:
    """[8] 회고 루프. 1주부터 시작해 3개월/6개월/1년으로 이어진다."""
    _load_session(session_id)
    retro.session_id = session_id
    storage.put_retrospective(session_id, retro.horizon.value, retro.model_dump(mode="json"))
    return ApiResponse.success(retro)


# 별도 라우터로 분리한다. /sessions 아래에 두면 /sessions/{session_id} 가
# 먼저 매칭되어 세션 조회로 흘러간다.
value_router = APIRouter(prefix="/value-map", tags=["value-map"])


@value_router.get("", response_model=ApiResponse[ValueMap])
async def get_value_map() -> ApiResponse[ValueMap]:
    """[8] 가치관 지도. 고민들을 가로질러 반복되는 축을 집계한다."""
    return ApiResponse.success(value_map_service.build_value_map())
