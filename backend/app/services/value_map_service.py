"""[8] 가치관 지도.

개별 고민 안에서는 선호밖에 안 보인다. 가치관은 **고민들을 가로질러** 반복되는
축에서 나온다 — 그래서 이 계산은 세션 단위가 아니라 전체 이력 단위다.

집계 기준은 우리가 판정한 lean이 아니라 사용자가 자기 입으로 말한
`annotation.self_lean_option_id`다. 자기가 말한 것만이 자기 가치관이다.
"""

from __future__ import annotations

from collections import defaultdict

from app.core import storage
from app.schemas.decision import Decision
from app.schemas.session import Session, ValueAxisEntry, ValueMap


def build_value_map(user_id: str) -> ValueMap:
    """★사람별로 집계한다. user_id 없이 부르면 남의 기록이 내 지도에 들어온다."""
    decisions = {
        raw["id"]: Decision.model_validate(raw)
        for raw in storage.list_all("decisions", user_id=user_id)
    }

    by_axis: dict[str, list[tuple[Session, Decision]]] = defaultdict(list)
    for raw in storage.list_all("sessions", user_id=user_id):
        session = Session.model_validate(raw)
        decision = decisions.get(session.decision_id)
        if decision is None or not decision.value_axis:
            continue
        by_axis[decision.value_axis].append((session, decision))

    axes = []
    # ★많이 반복된 축부터. 가나다순으로 놓으면 한 번씩 나온 축들 사이에
    # 열 번 반복된 축이 파묻힌다 — 가치관은 반복에서 나오는데 그게 안 보인다.
    ordered = sorted(by_axis.items(), key=lambda item: (-len(item[1]), item[0]))
    for axis, entries in ordered:
        counts, unlabelled = _count_sides(entries)
        axes.append(
            ValueAxisEntry(
                axis=axis,
                session_ids=[s.id for s, _ in entries],
                side_counts=counts,
                unlabelled_count=unlabelled,
                lean_pattern=_summarize(counts, unlabelled),
            )
        )
    return ValueMap(axes=axes)


def _count_sides(entries: list[tuple[Session, Decision]]) -> tuple[dict[str, int], int]:
    """극별 횟수와, 극을 붙이지 못해 빠진 기록 수.

    ★세는 것은 선택지 라벨이 아니라 `axis_side`(축의 극)다.
    라벨은 고민마다 다르다("이직한다" / "대학원 간다" / "사이드를 시작한다").
    라벨을 세면 "1회, 1회, 1회"가 나올 뿐 축을 가로지르는 패턴이 보이지 않는다.

    기준은 우리 판정이 아니라 `annotation.self_lean_option_id` —
    사용자가 자기 입으로 말한 것이다. 자기가 말한 것만이 자기 가치관이다.
    """
    counts: dict[str, int] = defaultdict(int)
    unlabelled = 0
    for session, decision in entries:
        chosen = session.annotation.self_lean_option_id if session.annotation else None
        if chosen is None:
            continue
        for option in decision.options:
            if option.id != chosen:
                continue
            if option.axis_side:
                counts[option.axis_side] += 1
            else:
                unlabelled += 1

    # 많은 쪽부터. 화면이 이 순서 그대로 막대를 그린다.
    ordered = dict(sorted(counts.items(), key=lambda item: -item[1]))
    return ordered, unlabelled


def _summarize(counts: dict[str, int], unlabelled: int) -> str:
    """관찰 한 문장.

    "당신은 성장을 중시하는 사람입니다" 같은 규정은 하지 않는다.
    그건 사용자가 지도를 보고 스스로 내릴 결론이다.
    """
    if not counts:
        if unlabelled:
            # 기록은 있는데 축을 나누지 못한 경우다. "부족하다"고 하면 사실과 다르다.
            return f"기록 {unlabelled}건이 있지만 축의 양쪽을 나누지 못했어요."
        return "아직 기록이 부족해요."

    total = sum(counts.values())
    summary = f"{total}번의 기록 중 — " + ", ".join(
        f"{side} {n}회" for side, n in counts.items()
    )
    if unlabelled:
        # 극을 못 붙인 기록은 조용히 빼지 않고 밝힌다. 지도의 신뢰도는 사용자가 판단한다.
        summary += f" (축을 나누지 못한 기록 {unlabelled}건 제외)"
    return summary
