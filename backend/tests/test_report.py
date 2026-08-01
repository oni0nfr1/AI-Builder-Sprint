"""[5] 리포트 검증 — 절대 규칙이 코드로 지켜지는지.

추천 금지·결론 금지·라벨 금지는 스타일이 아니라 제품 메커니즘의 필수 조건이다.
여기서 깨지면 실패 모드 ②(결과만 소비)를 그대로 재생산한다.
"""

from __future__ import annotations

import asyncio

import pytest

from app.schemas.analysis import (
    Delta,
    Lean,
    PreferenceDelta,
    PreferenceVerdict,
    StateDelta,
    StateLabel,
    StateVerdict,
    Verdict,
)
from app.schemas.common import MetricKey
from app.schemas.decision import Decision, Option
from app.schemas.session import Session
from app.services.report_service import build_report

FORBIDDEN = [
    # 결정 대행
    "추천", "권해", "권합니다", "낫습니다", "나아요", "맞습니다", "선택하세요",
    "하시는 게", "하는 게 좋", "바람직",
    # 감정 라벨 단정
    "불안하", "긴장하신", "확신이", "두려워", "설레시",
    # 원인 추정
    "때문에",
]


def _decision() -> Decision:
    return Decision(
        raw_input="이직할지 말지",
        title="이직할지 말지",
        value_axis="안정 vs 성장",
        options=[
            Option(id="opt-a", label="이직한다", imagine_prompt="", speak_prompt="", order_index=0),
            Option(id="opt-b", label="남는다", imagine_prompt="", speak_prompt="", order_index=1),
        ],
    )


def _verdict(lean: Lean, state: StateLabel, lean_option_id: str | None = "opt-a") -> Verdict:
    return Verdict(
        session_id="s1",
        preference=PreferenceVerdict(
            lean=lean,
            lean_option_id=lean_option_id if lean in (Lean.A, Lean.B) else None,
            magnitude=0.3,
            confidence=0.6,
            contributing={
                MetricKey.F0_MEAN: 0.18,
                MetricKey.SPEECH_RATE: 0.12,
                MetricKey.BPM: -0.09,
                MetricKey.PAUSE_RATIO: 0.02,  # 임계 미만 — 보고되지 않아야 한다
            },
        ),
        state=StateVerdict(label=state, magnitude=0.25),
    )


def _delta() -> Delta:
    return Delta(
        session_id="s1",
        preference=PreferenceDelta(option_a_id="opt-a", option_b_id="opt-b", per_metric={}),
        state=StateDelta(per_metric={}, default_available=True),
    )


def _build(verdict: Verdict) -> object:
    """LLM 키가 없으므로 규칙 기반 폴백 경로를 탄다."""
    return asyncio.run(
        build_report(verdict, _delta(), _decision(), Session(decision_id="dec-1"))
    )


def _all_text(report) -> str:
    return " ".join(
        [report.state_note, *report.observations, report.tagging_question,
         report.self_statement_question]
    )


@pytest.mark.parametrize("lean", list(Lean))
@pytest.mark.parametrize("state", list(StateLabel))
def test_no_forbidden_language(lean: Lean, state: StateLabel) -> None:
    """어떤 판정 조합에서도 추천·라벨·원인추정 표현이 나오면 안 된다."""
    text = _all_text(_build(_verdict(lean, state)))
    for phrase in FORBIDDEN:
        assert phrase not in text, f"금지 표현 '{phrase}'이 리포트에 나왔다: {text}"


def test_report_has_all_four_parts() -> None:
    """순서가 곧 설계다: 상태 고지 → 관찰 → 태깅 → 자기 진술."""
    report = _build(_verdict(Lean.A, StateLabel.CALM))
    assert report.state_note
    assert report.observations
    assert report.tagging_question
    assert report.body_tag_options
    assert report.self_statement_question


def test_tagging_question_points_at_lean_option() -> None:
    """비대칭 질문 — 신호가 강한 쪽으로 향한다. 유도가 일어나는 유일한 지점."""
    report = _build(_verdict(Lean.A, StateLabel.CALM, lean_option_id="opt-a"))
    assert "이직한다" in report.tagging_question
    assert report.tagging_option_id == "opt-a"


def test_no_option_is_singled_out_without_lean() -> None:
    """기울기가 없으면 특정 선택지를 지목하지 않는다."""
    for lean in (Lean.NONE, Lean.CONTRADICTORY):
        report = _build(_verdict(lean, StateLabel.CALM))
        assert report.tagging_option_id is None


def test_state_note_reflects_state() -> None:
    """상태 고지가 상태마다 달라야 사용자가 이번 기록의 신뢰도를 스스로 판단할 수 있다."""
    notes = {
        state: _build(_verdict(Lean.A, state)).state_note for state in StateLabel
    }
    assert len(set(notes.values())) == len(StateLabel)


def test_observations_skip_negligible_metrics() -> None:
    """차이가 미미한 지표까지 늘어놓으면 관찰이 노이즈가 된다."""
    report = _build(_verdict(Lean.A, StateLabel.CALM))
    assert not any("말 사이 쉼" in line for line in report.observations)
    assert any("목소리 높이" in line for line in report.observations)


def test_observations_are_comparisons_not_verdicts() -> None:
    """각 관찰은 두 선택지의 비교여야 한다 — 한쪽만 평가하면 결론이 된다."""
    report = _build(_verdict(Lean.A, StateLabel.CALM))
    for line in report.observations:
        assert "이직한다" in line and "남는다" in line


def test_self_statement_is_fixed() -> None:
    """자기 진술 질문은 표현이 흔들리면 유도가 섞이므로 고정한다."""
    a = _build(_verdict(Lean.A, StateLabel.AROUSED)).self_statement_question
    b = _build(_verdict(Lean.B, StateLabel.FLAT)).self_statement_question
    assert a == b
    assert a.endswith("?")
