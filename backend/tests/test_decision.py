"""[0] 고민 등록 — 상상 프롬프트의 중립성.

★어느 한쪽에 권하는 뉘앙스가 섞이면 [5] 리포트에 도달하기 전에 이미 유도가
일어나고, 그 시점부터 우리가 재는 건 사용자의 직관이 아니라 우리 프롬프트의
효과다 (CLAUDE.md).

실제로 이런 게 사용자에게 나갔다:
    "따뜻한 물줄기를 맞으며 피로가 풀리는 순간"
    "작업 흐름을 유지하며 결과물을 완성해 가는 순간"
한쪽은 감각적이고 유혹적이고, 다른 쪽은 건조하다. 게다가 "피로가 풀린다"는
결과를 우리가 단정했다 — 사용자는 자기 상상이 아니라 우리 시나리오를 떠올린다.

프롬프트로만 막으면 샌다. 코드로 막는다.
"""

from __future__ import annotations

import asyncio

import pytest

from app.schemas.decision import Decision, Option
from app.services import decision_service
from app.services.decision_service import parse_decision


def _option(label: str, imagine: str) -> Option:
    return Option(label=label, imagine_prompt=imagine, speak_prompt="느낌을 말해주세요.")


def _decision(*prompts: str) -> Decision:
    return Decision(
        raw_input="x",
        title="x",
        value_axis="A vs B",
        options=[_option(f"선택{i}", p) for i, p in enumerate(prompts)],
    )


# ── 유인가 차단 ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "polluted",
    [
        "따뜻한 물줄기를 맞으며 피로가 풀리는 순간을 떠올려보세요.",
        "뿌듯하게 결과물을 완성해 가는 순간을 떠올려보세요.",
        "편안하게 쉬고 있는 자신을 떠올려보세요.",
        "지치고 답답한 자신을 떠올려보세요.",
    ],
)
def test_valenced_prompt_is_rejected(polluted: str) -> None:
    """장면의 성질을 우리가 정해주면 사용자는 자기 상상을 못 한다."""
    ok = "그 장면을 떠올려보세요. 무엇이 보이고 무엇이 느껴지나요?"
    assert not decision_service._prompts_are_neutral(_decision(polluted, ok).options)


def test_neutral_symmetric_prompts_pass() -> None:
    """검증은 오염된 것만 걸러야 한다. 멀쩡한 걸 버리면 LLM 을 쓸 이유가 없다."""
    decision = _decision(
        "6개월 뒤 새 회사에서 일하고 있는 자신을 떠올려보세요. 무엇이 보이고 무엇이 느껴지나요?",
        "6개월 뒤 지금 회사에서 일하고 있는 자신을 떠올려보세요. 무엇이 보이고 무엇이 느껴지나요?",
    )
    assert decision_service._prompts_are_neutral(decision.options)


# ── 대칭성 ─────────────────────────────────────────────────


def test_asymmetric_prompts_are_rejected() -> None:
    """한쪽이 더 길거나 더 생생하면 그 자체가 유도다."""
    decision = _decision(
        "샤워를 하고 있는 순간을 아주 자세히, 물소리와 김이 서린 거울까지 하나하나 떠올려보세요.",
        "일하는 자신을 떠올려보세요.",
    )
    assert not decision_service._prompts_are_neutral(decision.options)


def test_empty_prompt_is_rejected() -> None:
    assert not decision_service._prompts_are_neutral(_decision("", "무언가를 떠올려보세요.").options)


# ── 되돌릴 때는 둘 다 ───────────────────────────────────────


def test_normalize_replaces_both_prompts() -> None:
    """한쪽만 고치면 비대칭이 그대로 남는다."""
    decision = _decision(
        "따뜻한 물줄기를 맞으며 피로가 풀리는 순간을 떠올려보세요.",
        "일하는 자신을 떠올려보세요. 무엇이 보이고 무엇이 느껴지나요?",
    )
    decision_service._normalize_prompts(decision)

    prompts = [o.imagine_prompt for o in decision.options]
    assert all("따뜻" not in p for p in prompts)
    # 선택지 이름만 빼면 같은 문장이어야 한다.
    tails = [p.split("'", 2)[-1] for p in prompts]
    assert tails[0] == tails[1]
    assert all("무엇이 보이고 무엇이 느껴지나요?" in p for p in prompts)


def test_fallback_prompt_invites_sensing_without_filling_it() -> None:
    """상상은 자극하되 느낌은 사용자가 채운다 — 절충안의 핵심."""
    prompt = decision_service._imagine_prompt("이직한다")
    assert "무엇이 보이고 무엇이 느껴지나요?" in prompt
    assert not any(word in prompt for word in decision_service._VALENCE_WORDS)


# ── 파이프라인 전체 ─────────────────────────────────────────


def test_parse_decision_without_llm_is_symmetric() -> None:
    """LLM 키가 없으면 폴백을 타는데, 그 경로도 대칭이어야 한다."""
    decision = asyncio.run(parse_decision("이직할지 남을지"))
    assert len(decision.options) == 2
    assert decision_service._prompts_are_neutral(decision.options)
    speak = {o.speak_prompt for o in decision.options}
    assert len(speak) == 1, "발화 프롬프트는 두 선택지가 완전히 같아야 한다"


def test_speak_prompt_asks_for_feeling_not_analysis() -> None:
    """장단점을 따지게 하면 목소리가 평탄해져 측정하려는 신호가 사라진다."""
    prompt = decision_service._speak_prompt("이직한다")
    assert "느낌" in prompt
    for banned in ("장단점", "이유", "왜", "설명"):
        assert banned not in prompt
