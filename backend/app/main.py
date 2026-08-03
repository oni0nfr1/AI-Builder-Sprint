"""직관 노트 백엔드.

파이프라인 골조는 CLAUDE.md §4, 계약은 docs/CONTRACTS.md 참조.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.storage import init_db
from app.routers import decisions, sessions

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="직관 노트 (Intuition Note)",
    description="고민 중인 선택지 앞에서 내 언어·비언어 신호가 어떻게 반응하는지 비추는 메타인지 훈련 도구",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(decisions.router)
app.include_router(sessions.router)
app.include_router(sessions.value_router)
app.include_router(sessions.conviction_router)


def _envelope(code: str, message: str, status: int) -> JSONResponse:
    """팀 컨벤션 응답 형식으로 변환. raw traceback은 절대 노출하지 않는다."""
    return JSONResponse(
        status_code=status,
        content={"ok": False, "data": None, "error": {"code": code, "message": message}},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return _envelope("http_error", str(exc.detail), exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return _envelope("validation_error", "요청 형식이 올바르지 않습니다.", 422)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled error on %s", request.url.path)
    return _envelope("internal_error", "서버 내부 오류가 발생했습니다.", 500)


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "ok": True,
        "data": {"status": "up", "llm_enabled": settings.llm_enabled},
        "error": None,
    }
