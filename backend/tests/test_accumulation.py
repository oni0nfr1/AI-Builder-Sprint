"""[8] 축적 — 가치관 지도(2층)와 확신(3층).

    1회   → 선호
    반복  → 가치관    ← value_map
    3개월 → 확신      ← conviction

가장 중요한 검증은 **무엇을 세는가**다. 선택지 라벨을 세면 고민마다 라벨이 달라
"1회, 1회, 1회"가 나올 뿐 축을 가로지르는 패턴이 보이지 않는다. 축의 극을 세야 한다.
"""

from __future__ import annotations

import pytest

from app.core import storage
from app.core.config import get_settings
from app.schemas.decision import Decision, Option
from app.schemas.report import Annotation
from app.schemas.session import Horizon, Retrospective, Session
from app.services.conviction_service import build_conviction
from app.services.value_map_service import build_value_map


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """실제 DB를 건드리지 않는다."""
    get_settings.cache_clear()
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    storage.init_db()
    yield
    get_settings.cache_clear()


def _record(
    key: str,
    *,
    axis: str,
    labels: tuple[str, str],
    sides: tuple[str | None, str | None],
    self_lean: int,
    retro: tuple[int, int] | None = None,
) -> None:
    """고민 + 세션(+회고) 한 벌을 저장한다. retro 는 (고른 쪽, 만족도)."""
    decision = Decision(
        id=f"d{key}",
        raw_input=axis,
        title=axis,
        value_axis=axis,
        options=[
            Option(
                id=f"o{key}-{i}",
                label=label,
                axis_side=side,
                imagine_prompt="",
                speak_prompt="",
                order_index=i,
            )
            for i, (label, side) in enumerate(zip(labels, sides))
        ],
    )
    session = Session(
        id=f"s{key}",
        decision_id=decision.id,
        annotation=Annotation(
            session_id=f"s{key}",
            self_lean_option_id=decision.options[self_lean].id,
        ),
    )
    storage.put("decisions", decision.id, decision.model_dump(mode="json"))
    storage.put(
        "sessions", session.id, session.model_dump(mode="json"), decision_id=decision.id
    )
    if retro is not None:
        chosen, satisfaction = retro
        entry = Retrospective(
            session_id=session.id,
            horizon=Horizon.M3,
            chosen_option_id=decision.options[chosen].id,
            satisfaction=satisfaction,
        )
        storage.put_retrospective(session.id, Horizon.M3.value, entry.model_dump(mode="json"))


# ── 2층: 가치관 ─────────────────────────────────────────────


def test_pattern_counts_axis_sides_not_labels() -> None:
    """★핵심. 라벨은 고민마다 다르므로 극으로 모아야 패턴이 드러난다."""
    _record("1", axis="안정 vs 성장", labels=("남는다", "옮긴다"),
            sides=("안정", "성장"), self_lean=1)
    _record("2", axis="안정 vs 성장", labels=("실무를 잇는다", "대학원에 간다"),
            sides=("안정", "성장"), self_lean=1)
    _record("3", axis="안정 vs 성장", labels=("쉰다", "사이드를 시작한다"),
            sides=("안정", "성장"), self_lean=1)

    axis = build_value_map().axes[0]
    assert "성장 3회" in axis.lean_pattern
    # 라벨이 그대로 새면 "1회, 1회, 1회"가 되어 패턴이 사라진다.
    for label in ("옮긴다", "대학원에 간다", "사이드를 시작한다"):
        assert label not in axis.lean_pattern


def test_split_axis_is_reported_as_split() -> None:
    """갈리는 축을 한쪽으로 몰아 보여주면 없는 가치관을 만들어내는 것이다."""
    _record("1", axis="관계 vs 자율", labels=("모인다", "혼자 쉰다"),
            sides=("관계", "자율"), self_lean=0)
    _record("2", axis="관계 vs 자율", labels=("친구 근처", "회사 근처"),
            sides=("관계", "자율"), self_lean=0)
    _record("3", axis="관계 vs 자율", labels=("가족 행사", "혼자 시간"),
            sides=("관계", "자율"), self_lean=1)

    pattern = build_value_map().axes[0].lean_pattern
    assert "관계 2회" in pattern and "자율 1회" in pattern


def test_unlabelled_records_are_disclosed_not_dropped() -> None:
    """축을 못 나눈 기록을 조용히 빼면 지도의 신뢰도를 사용자가 판단할 수 없다."""
    _record("1", axis="안정 vs 성장", labels=("남는다", "옮긴다"),
            sides=("안정", "성장"), self_lean=1)
    _record("2", axis="안정 vs 성장", labels=("A", "B"),
            sides=(None, None), self_lean=1)

    pattern = build_value_map().axes[0].lean_pattern
    assert "성장 1회" in pattern
    assert "1건 제외" in pattern


def test_all_unlabelled_says_so_rather_than_insufficient() -> None:
    """기록이 있는데 '부족하다'고 하면 사실과 다르다."""
    _record("1", axis="안정 vs 성장", labels=("A", "B"),
            sides=(None, None), self_lean=0)
    assert "나누지 못했" in build_value_map().axes[0].lean_pattern


def test_pattern_uses_self_statement_not_our_verdict() -> None:
    """집계 기준은 사용자가 자기 입으로 말한 것이다. 자기가 말한 것만이 자기 가치관이다."""
    decision = Decision(
        id="d1", raw_input="x", title="x", value_axis="안정 vs 성장",
        options=[
            Option(id="o1", label="남는다", axis_side="안정",
                   imagine_prompt="", speak_prompt="", order_index=0),
            Option(id="o2", label="옮긴다", axis_side="성장",
                   imagine_prompt="", speak_prompt="", order_index=1),
        ],
    )
    # annotation 이 없으면 우리 판정이 있어도 집계되지 않아야 한다.
    session = Session(id="s1", decision_id="d1")
    storage.put("decisions", "d1", decision.model_dump(mode="json"))
    storage.put("sessions", "s1", session.model_dump(mode="json"), decision_id="d1")

    assert build_value_map().axes[0].lean_pattern == "아직 기록이 부족해요."


# ── 3층: 확신 ───────────────────────────────────────────────


def test_conviction_contrasts_followed_and_diverged() -> None:
    """그때 말한 마음대로 골랐을 때와 아닐 때를 나란히 놓는다."""
    _record("1", axis="안정 vs 성장", labels=("남는다", "옮긴다"),
            sides=("안정", "성장"), self_lean=1, retro=(1, 5))
    _record("2", axis="안정 vs 성장", labels=("쉰다", "시작한다"),
            sides=("안정", "성장"), self_lean=1, retro=(1, 3))
    _record("3", axis="관계 vs 자율", labels=("모인다", "쉰다"),
            sides=("관계", "자율"), self_lean=0, retro=(1, 2))

    conviction = build_conviction()
    followed = next(g for g in conviction.groups if g.followed_intuition)
    diverged = next(g for g in conviction.groups if not g.followed_intuition)

    assert followed.count == 2 and followed.average_satisfaction == 4.0
    assert diverged.count == 1 and diverged.average_satisfaction == 2.0
    assert conviction.total_retrospectives == 3


def test_conviction_note_is_observation_not_conclusion() -> None:
    """"당신의 직관은 정확합니다"는 결정 대행이다. 숫자를 나란히 놓기만 한다."""
    _record("1", axis="안정 vs 성장", labels=("남는다", "옮긴다"),
            sides=("안정", "성장"), self_lean=1, retro=(1, 5))
    _record("2", axis="안정 vs 성장", labels=("쉰다", "시작한다"),
            sides=("안정", "성장"), self_lean=1, retro=(0, 2))

    note = build_conviction().note
    for phrase in ("정확", "믿을 만", "추천", "권", "따르세요", "맞았"):
        assert phrase not in note


def test_conviction_waits_for_enough_records() -> None:
    """회고 한 건으로 확신을 말하면 근거 없는 규정이 된다."""
    _record("1", axis="안정 vs 성장", labels=("남는다", "옮긴다"),
            sides=("안정", "성장"), self_lean=1, retro=(1, 5))
    assert "쌓이면" in build_conviction().note


def test_conviction_ignores_retrospectives_without_self_statement() -> None:
    """자기 진술이 없으면 대조할 기준점이 없다."""
    decision = Decision(
        id="d1", raw_input="x", title="x", value_axis="안정 vs 성장",
        options=[
            Option(id="o1", label="남는다", axis_side="안정",
                   imagine_prompt="", speak_prompt="", order_index=0),
            Option(id="o2", label="옮긴다", axis_side="성장",
                   imagine_prompt="", speak_prompt="", order_index=1),
        ],
    )
    session = Session(id="s1", decision_id="d1")  # annotation 없음
    storage.put("decisions", "d1", decision.model_dump(mode="json"))
    storage.put("sessions", "s1", session.model_dump(mode="json"), decision_id="d1")
    retro = Retrospective(
        session_id="s1", horizon=Horizon.M3, chosen_option_id="o2", satisfaction=5
    )
    storage.put_retrospective("s1", Horizon.M3.value, retro.model_dump(mode="json"))

    conviction = build_conviction()
    assert conviction.total_retrospectives == 1
    assert all(g.count == 0 for g in conviction.groups)


def test_empty_history_is_safe() -> None:
    assert build_value_map().axes == []
    assert build_conviction().total_retrospectives == 0


def test_side_counts_are_ordered_by_frequency() -> None:
    """화면이 이 순서대로 막대를 그린다. 많은 쪽이 먼저 와야 읽힌다."""
    _record("1", axis="안정 vs 성장", labels=("남는다", "옮긴다"),
            sides=("안정", "성장"), self_lean=1)
    _record("2", axis="안정 vs 성장", labels=("쉰다", "시작한다"),
            sides=("안정", "성장"), self_lean=1)
    _record("3", axis="안정 vs 성장", labels=("유지", "전환"),
            sides=("안정", "성장"), self_lean=0)

    axis = build_value_map().axes[0]
    assert list(axis.side_counts.items()) == [("성장", 2), ("안정", 1)]
    assert axis.unlabelled_count == 0


def test_unlabelled_count_is_exposed_separately() -> None:
    """문장에만 묻어두면 화면이 비율 막대의 신뢰도를 표시할 수 없다."""
    _record("1", axis="안정 vs 성장", labels=("남는다", "옮긴다"),
            sides=("안정", "성장"), self_lean=1)
    _record("2", axis="안정 vs 성장", labels=("A", "B"),
            sides=(None, None), self_lean=0)

    axis = build_value_map().axes[0]
    assert axis.side_counts == {"성장": 1}
    assert axis.unlabelled_count == 1
