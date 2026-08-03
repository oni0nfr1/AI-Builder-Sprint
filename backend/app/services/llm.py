"""Upstage Solar 클라이언트.

API 키가 없으면 호출하지 않고 None을 반환한다 — 각 서비스는 규칙 기반
폴백을 갖고 있어서, 키 없이도 파이프라인 전체가 동작한다.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_TIMEOUT_SEC = 30.0


async def chat_json(
    system: str, user: str, *, temperature: float = 0.3
) -> dict[str, Any] | None:
    """JSON 응답을 요구하는 대화 호출. 실패 시 None (호출부가 폴백한다)."""
    settings = get_settings()
    if not settings.llm_enabled:
        return None

    payload = {
        "model": settings.upstage_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SEC) as client:
            response = await client.post(
                f"{settings.upstage_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.upstage_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        logger.exception("Solar 호출 실패 — 규칙 기반 폴백으로 진행")
        return None


async def embed_text(text: str) -> list[float] | None:
    """발화 내용 → 의미 벡터 (4096차원).

    별도 임베딩 모델을 로컬에 두지 않는다. 이미 Solar 를 쓰고 있고, 수백 MB 를
    더 받을 이유가 없다. 실패하면 None — 잠재 축만 빠지고 나머지는 그대로 돈다.
    """
    settings = get_settings()
    if not settings.llm_enabled or not text.strip():
        return None

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SEC) as client:
            response = await client.post(
                f"{settings.upstage_base_url}/embeddings",
                headers={"Authorization": f"Bearer {settings.upstage_api_key}"},
                json={"model": settings.upstage_embedding_model, "input": text},
            )
            response.raise_for_status()
            return [float(x) for x in response.json()["data"][0]["embedding"]]
    except Exception:
        logger.warning("임베딩 호출 실패 — 잠재 축 없이 진행", exc_info=True)
        return None
