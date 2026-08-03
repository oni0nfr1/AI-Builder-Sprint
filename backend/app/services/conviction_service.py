"""[8] 확신 (3층).

    1회   → 선호      "고민 중인 줄 알았는데 사실 B에 마음이 가 있구나"
    반복  → 가치관    "나는 이런 걸 중요하게 여기는 사람이구나"
    3개월 → **확신**  "내 직관은 믿을 만하구나"      ← 여기

세 번째 층은 시간이 지나야만 생긴다. 그때 무엇을 골랐고 지금 얼마나 만족하는지를,
**그때 자기 입으로 말한 것**과 대조해야 나온다.

★비교 기준이 우리 판정(`verdict.preference.lean`)이 아니라
`annotation.self_lean_option_id`인 이유: 자기가 말한 것만이 자기 기준점이 된다.
우리 판정과 맞춰보면 "우리 예측이 맞았다"는 이야기가 되고, 그건 이 제품이 아니다.

그리고 결론을 내지 않는다. 두 무리를 나란히 놓을 뿐이다.
"당신의 직관은 정확합니다"는 결정 대행이며 절대 규칙 ①② 위반이다.
"""

from __future__ import annotations

from app.core import storage
from app.schemas.session import Conviction, ConvictionGroup, Retrospective, Session

MIN_RETROSPECTIVES = 2
"""이보다 적으면 대조가 의미를 갖지 못한다."""


def build_conviction(user_id: str) -> Conviction:
    """★사람별로 집계한다. 남의 만족도가 내 확신의 근거가 되면 안 된다."""
    self_leans = {
        session.id: session.annotation.self_lean_option_id
        for session in (
            Session.model_validate(raw)
            for raw in storage.list_all("sessions", user_id=user_id)
        )
        if session.annotation and session.annotation.self_lean_option_id
    }

    followed: list[int] = []
    diverged: list[int] = []
    total = 0
    for raw in storage.list_retrospectives(user_id=user_id):
        retro = Retrospective.model_validate(raw)
        total += 1
        stated = self_leans.get(retro.session_id)
        if stated is None or retro.chosen_option_id is None:
            # 자기 진술이 없거나 무엇을 골랐는지 모르면 대조할 수 없다.
            continue
        bucket = followed if retro.chosen_option_id == stated else diverged
        bucket.append(retro.satisfaction)

    groups = [
        _group(followed_intuition=True, scores=followed),
        _group(followed_intuition=False, scores=diverged),
    ]
    return Conviction(
        total_retrospectives=total,
        groups=groups,
        note=_note(followed, diverged),
    )


def _group(*, followed_intuition: bool, scores: list[int]) -> ConvictionGroup:
    return ConvictionGroup(
        followed_intuition=followed_intuition,
        count=len(scores),
        average_satisfaction=round(sum(scores) / len(scores), 2) if scores else None,
    )


def _note(followed: list[int], diverged: list[int]) -> str:
    """관찰 한 문장. 판정도 격려도 하지 않는다."""
    if len(followed) + len(diverged) < MIN_RETROSPECTIVES:
        return "회고가 더 쌓이면 그때 말한 마음과 지금의 만족을 나란히 놓아드릴게요."

    if not followed:
        return f"자기 진술과 다르게 고른 {len(diverged)}번의 기록이 있어요."
    if not diverged:
        avg = sum(followed) / len(followed)
        return (
            f"자기 진술대로 고른 {len(followed)}번의 만족도는 평균 {avg:.1f}점이었어요. "
            "아직 다르게 고른 기록이 없어 견줄 대상은 없습니다."
        )

    return (
        f"자기 진술대로 고른 {len(followed)}번은 평균 {sum(followed) / len(followed):.1f}점, "
        f"다르게 고른 {len(diverged)}번은 평균 {sum(diverged) / len(diverged):.1f}점이었어요."
    )
