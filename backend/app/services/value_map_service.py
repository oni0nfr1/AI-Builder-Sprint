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


def build_value_map() -> ValueMap:
    decisions = {
        raw["id"]: Decision.model_validate(raw) for raw in storage.list_all("decisions")
    }

    by_axis: dict[str, list[tuple[Session, Decision]]] = defaultdict(list)
    for raw in storage.list_all("sessions"):
        session = Session.model_validate(raw)
        decision = decisions.get(session.decision_id)
        if decision is None or not decision.value_axis:
            continue
        by_axis[decision.value_axis].append((session, decision))

    axes = []
    for axis, entries in sorted(by_axis.items()):
        axes.append(
            ValueAxisEntry(
                axis=axis,
                session_ids=[s.id for s, _ in entries],
                lean_pattern=_summarize(entries),
            )
        )
    return ValueMap(axes=axes)


def _summarize(entries: list[tuple[Session, Decision]]) -> str:
    """이 축에서 사용자가 반복적으로 어느 쪽을 택했나.

    관찰만 서술한다 — "당신은 성장을 중시하는 사람입니다" 같은 규정은 하지 않는다.
    그건 사용자가 지도를 보고 스스로 내릴 결론이다.
    """
    counts: dict[str, int] = defaultdict(int)
    for session, decision in entries:
        chosen = session.annotation.self_lean_option_id if session.annotation else None
        if chosen is None:
            continue
        for option in decision.options:
            if option.id == chosen:
                counts[option.label] += 1

    if not counts:
        return "아직 기록이 부족해요."

    total = sum(counts.values())
    parts = [f"{label} {n}회" for label, n in sorted(counts.items(), key=lambda x: -x[1])]
    return f"{total}번의 기록 중 — " + ", ".join(parts)
