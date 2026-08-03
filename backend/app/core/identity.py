"""사용자 식별.

인증은 없다. 브라우저가 UUID 를 만들어 `localStorage` 에 두고 헤더로 보낸다.

계정을 만들라고 하는 순간 사람은 진짜 고민을 말하지 않는다. 우리가 다루는 건
몸이 흘리는 신호이고, 그 신뢰가 없으면 제품이 성립하지 않는다 (CLAUDE.md §6).
헤더가 없으면 단일 사용자(`local`)로 본다 — 기존 저장분과 개발 중 호출을 위해서다.

★식별자가 있어야 하는 이유는 개인화만이 아니다. 없으면 [8] 축적이 **남의 기록을
내 것처럼** 집계한다.
"""

from __future__ import annotations

import re

from fastapi import Header

from app.core.storage import DEFAULT_USER_ID

USER_HEADER = "X-User-Id"

_ALLOWED = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def current_user(x_user_id: str | None = Header(default=None)) -> str:
    """헤더에서 사용자 식별자를 읽는다. 형식이 어긋나면 기본 사용자로 본다.

    SQL 은 파라미터 바인딩을 쓰지만, 이 값이 로그와 파일 이름으로도 흘러가므로
    모양을 여기서 한 번 좁힌다.
    """
    if x_user_id and _ALLOWED.match(x_user_id):
        return x_user_id
    return DEFAULT_USER_ID
