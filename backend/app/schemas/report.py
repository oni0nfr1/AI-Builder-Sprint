"""[5] 리포트 + [6] 사용자 태깅 — Report / Annotation.

리포트의 하드 제약 (어기면 제품이 성립하지 않는다):

    ✗ 어느 쪽이 낫다/맞다              → 결정 대행
    ✗ 감정 라벨 단정 ("불안하시군요")   → 결정 대행과 동일
    ✗ 원인 추정 ("~때문에")
    ✗ 조언·제안·격려

유도는 관찰이 아니라 질문에서 일어난다. `observations`는 데이터 번역일 뿐이고,
`tagging_question`의 *방향*이 우리가 쥔 유일한 핸들이다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Report(BaseModel):
    """사용자에게 보이는 유일한 산출물. 순서가 곧 설계다."""

    state_note: str
    """① 상태 고지. 프레임이므로 가장 먼저 나온다.

    이게 있어야 사용자가 이번 기록을 얼마나 믿을지 스스로 판단할 수 있고,
    그 판단 자체가 메타인지 훈련이다.
    """

    observations: list[str] = Field(default_factory=list)
    """② 관찰만. 판정·라벨·원인추정 없음."""

    tagging_question: str
    """③ 비대칭 질문 — 신호가 강한 쪽으로 향한다."""

    tagging_option_id: str | None = None
    """③이 어느 선택지를 향한 질문인지. 태그를 귀속시키는 데 필요하다.

    질문 문구에 이미 그 선택지 이름이 드러나므로 새로 노출되는 정보는 없다.
    `lean`이나 `confidence` 같은 판정값은 여전히 나가지 않는다.
    """

    body_tag_options: list[str] = Field(default_factory=list)
    """예: ["가슴 답답", "손끝 떨림", "설렘", "찜찜함"]"""

    self_statement_question: str
    """④ "지금은 어느 쪽에 마음이 더 가 있는 것 같으세요?" """


DEFAULT_BODY_TAGS: list[str] = [
    "가슴 답답함",
    "손끝 떨림",
    "설렘",
    "이유 없는 찜찜함",
    "몸이 가벼움",
    "목이 조임",
    "아무 느낌 없음",
]


class Annotation(BaseModel):
    """사용자가 남기는 해석. 해석의 주체는 항상 사용자다."""

    session_id: str
    option_id: str | None = None
    body_tags: list[str] = Field(default_factory=list)
    body_tag_custom: str | None = None

    self_lean_option_id: str | None = None
    """★이 제품의 핵심 산출물.

    우리가 판정한 `verdict.preference.lean`이 아니라, **사용자가 자기 입으로 말한 것**이
    저장되고 회고의 기준점이 된다. 사용자가 자기 입으로 말해야 자기 결정이 된다.
    """

    self_lean_note: str | None = None
