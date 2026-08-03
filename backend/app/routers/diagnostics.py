"""개발 전용 진단 API. 요청과 결과를 DB에 저장하지 않는다."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.schemas.common import ApiResponse
from app.schemas.diagnostics import RppgComparisonRequest, RppgComparisonResult
from app.services.rppg import estimate_heart_rate

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.post("/rppg/compare", response_model=ApiResponse[RppgComparisonResult])
def compare_rppg(req: RppgComparisonRequest) -> ApiResponse[RppgComparisonResult]:
    """같은 구간의 레거시 CHROM과 rppg-web 결과를 나란히 반환한다.

    RGB 시계열은 이 함수 안에서만 사용하며 storage 계층을 호출하지 않는다.
    """
    if not get_settings().rppg_diagnostics_enabled:
        raise HTTPException(status_code=404, detail="rPPG 진단 모드가 비활성화되어 있습니다.")

    server = (
        estimate_heart_rate(req.rgb_series, req.fps)
        if req.rgb_series is not None
        else None
    )
    reference = req.reference_bpm
    web_bpm = req.rppg_web.bpm if req.rppg_web is not None else None

    return ApiResponse.success(
        RppgComparisonResult(
            server_chrom=server,
            rppg_web=req.rppg_web,
            reference_bpm=reference,
            server_absolute_error=(
                round(abs(server.bpm - reference), 2)
                if reference is not None and server is not None
                else None
            ),
            web_absolute_error=(
                round(abs(web_bpm - reference), 2)
                if reference is not None and web_bpm is not None
                else None
            ),
            bpm_difference=(
                round(abs(server.bpm - web_bpm), 2)
                if server is not None and web_bpm is not None
                else None
            ),
        )
    )
