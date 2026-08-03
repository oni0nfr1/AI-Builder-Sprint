"""[5] 리포트의 **LLM 경로** 검증.

test_report.py는 LLM 키가 없는 환경에서 돌아 규칙 기반 폴백만 검증한다.
정작 사용자가 실제로 받는 건 Solar가 쓴 문장인데, 그 경로가 통째로 비어 있었다.

실제로 이런 문장이 사용자에게 나갔다:
    "현재 'flat' 상태에서 측정된 음성 변화를 바탕으로 기록을 남깁니다."
    "선택지 A를 말할 때 말 사이 쉼이 21.7% 더 길었고..."

내부 판정 용어가 그대로 노출됐고(절대 규칙 ② 위반), 선택지는 기호로 불려서
사용자가 자기 고민을 알아볼 수 없었다. 프롬프트로만 막으면 이렇게 샌다.
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
from app.services import report_service
from app.services.report_service import build_report

CLEAN = {
    "state_note": "오늘은 평소보다 신호가 가라앉은 상태에서 기록하셨어요.",
    "observations": [
        "'이직한다'를 말할 때 목소리가 더 높았고, '남는다'를 말할 때는 더 낮았어요",
    ],
    "tagging_question": "'이직한다'를 말할 때 몸에서 뭐가 느껴지셨어요?",
}


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


def _verdict() -> Verdict:
    return Verdict(
        session_id="s1",
        preference=PreferenceVerdict(
            lean=Lean.A,
            lean_option_id="opt-a",
            magnitude=0.3,
            confidence=0.6,
            contributing={MetricKey.F0_MEAN: 0.18, MetricKey.SPEECH_RATE: 0.12},
        ),
        state=StateVerdict(label=StateLabel.FLAT, magnitude=0.25),
    )


def _delta() -> Delta:
    return Delta(
        session_id="s1",
        preference=PreferenceDelta(option_a_id="opt-a", option_b_id="opt-b", per_metric={}),
        state=StateDelta(per_metric={}, default_available=True),
    )


def _build_with(monkeypatch: pytest.MonkeyPatch, payload: dict | None):
    """chat_json을 가로채 LLM 경로를 강제로 태운다."""

    async def fake_chat_json(_system: str, _user: str):
        return payload

    monkeypatch.setattr(report_service, "chat_json", fake_chat_json)
    return asyncio.run(
        build_report(_verdict(), _delta(), _decision(), Session(decision_id="dec-1"))
    )


# ── 내부 용어 누출 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "leaked",
    [
        "현재 'flat' 상태에서 측정된 음성 변화를 바탕으로 기록을 남깁니다.",
        "calm 상태로 보입니다.",
        "aroused 한 상태에서 기록하셨어요.",
        "confidence 0.72로 측정되었습니다.",
    ],
)
def test_internal_terms_never_reach_user(monkeypatch: pytest.MonkeyPatch, leaked: str) -> None:
    """내부 판정 용어가 섞이면 그 문장은 버리고 규칙 기반으로 되돌린다."""
    report = _build_with(monkeypatch, {**CLEAN, "state_note": leaked})
    assert report.state_note != leaked
    assert "flat" not in report.state_note.lower()
    assert report.state_note  # 비어 있으면 안 된다 — 상태 고지는 프레임이다


@pytest.mark.parametrize("symbolic", ["선택지 A", "선택지 B", "옵션 A", "Option B"])
def test_symbolic_option_names_are_rejected(
    monkeypatch: pytest.MonkeyPatch, symbolic: str
) -> None:
    """선택지를 기호로 부르면 사용자가 자기 고민을 알아볼 수 없다."""
    polluted = f"{symbolic}를 말할 때 말 사이 쉼이 21.7% 더 길었어요"
    report = _build_with(monkeypatch, {**CLEAN, "observations": [polluted]})
    assert polluted not in report.observations
    # 폴백 관찰에는 실제 선택지 이름이 들어간다.
    assert any("이직한다" in line for line in report.observations)


@pytest.mark.parametrize(
    "phrase",
    ["이직한다가 더 낫습니다.", "이직을 추천합니다.", "긴장했기 때문에 그렇습니다."],
)
def test_forbidden_phrases_from_llm_are_rejected(
    monkeypatch: pytest.MonkeyPatch, phrase: str
) -> None:
    """추천·결론·원인추정은 LLM이 썼더라도 사용자에게 가면 안 된다."""
    report = _build_with(monkeypatch, {**CLEAN, "tagging_question": phrase})
    assert report.tagging_question != phrase


# ── 정상 출력은 살린다 ──────────────────────────────────────────


def test_clean_llm_output_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    """검증은 오염된 것만 걸러야 한다. 멀쩡한 표현까지 버리면 LLM을 쓸 이유가 없다."""
    report = _build_with(monkeypatch, CLEAN)
    assert report.state_note == CLEAN["state_note"]
    assert report.observations == CLEAN["observations"]
    assert report.tagging_question == CLEAN["tagging_question"]


def test_partial_pollution_keeps_clean_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    """한 줄이 오염됐다고 나머지 관찰까지 버릴 이유는 없다."""
    clean_line = "'이직한다'를 말할 때 말속도가 더 빨랐어요"
    report = _build_with(
        monkeypatch,
        {**CLEAN, "observations": ["선택지 A가 더 낫습니다", clean_line]},
    )
    assert report.observations == [clean_line]


# ── LLM이 건드릴 수 없는 것 ─────────────────────────────────────


def test_self_statement_is_never_from_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """자기 진술 질문은 고정이다 — 표현이 흔들리면 유도가 섞인다."""
    report = _build_with(
        monkeypatch, {**CLEAN, "self_statement_question": "B로 하시겠어요?"}
    )
    assert report.self_statement_question == report_service._SELF_STATEMENT


def test_tagging_option_comes_from_verdict_not_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """어느 선택지를 물었는지는 판정에서 가져온다. LLM 자기 신고를 믿지 않는다."""
    report = _build_with(monkeypatch, {**CLEAN, "tagging_option_id": "opt-b"})
    assert report.tagging_option_id == "opt-a"


def test_llm_failure_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Solar가 죽어도 리포트는 나와야 한다."""
    report = _build_with(monkeypatch, None)
    assert report.state_note
    assert report.observations
    assert report.tagging_question


def test_empty_observations_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """관찰이 통째로 걸러지면 규칙 기반 관찰로 채운다 — 빈 리포트는 안 된다."""
    report = _build_with(monkeypatch, {**CLEAN, "observations": ["선택지 A가 낫습니다"]})
    assert report.observations
    assert any("이직한다" in line for line in report.observations)


def test_internal_verdict_is_not_in_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """리포트 어디에도 lean/confidence가 실려서는 안 된다 — 산파술의 전제다."""
    report = _build_with(monkeypatch, CLEAN)
    assert not hasattr(report, "lean")
    assert not hasattr(report, "confidence")
    dumped = report.model_dump_json()
    for term in ("lean", "confidence", "magnitude"):
        assert term not in dumped
