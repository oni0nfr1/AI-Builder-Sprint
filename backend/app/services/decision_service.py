"""[0] 고민 등록 — 한 문장에서 선택지·가치축·프롬프트를 뽑는다.

⚠️ 두 선택지의 상상/발화 프롬프트는 **구조적으로 대칭**이어야 한다.
어느 한쪽에 권하는 뉘앙스가 섞이면 [5] 리포트에 도달하기 전에 이미 유도가 일어나고,
그 시점부터 우리가 재는 건 사용자의 직관이 아니라 우리 프롬프트의 효과다.
"""

from __future__ import annotations

import random

from app.schemas.decision import Decision, Option
from app.services.korean import josa
from app.services.llm import chat_json

_SYSTEM = """당신은 사용자의 고민 한 문장을 구조화하는 파서다.

반드시 지킬 것:
1. 선택지는 정확히 2개. 사용자가 실제로 저울질하는 것이어야 한다.
2. 두 선택지 중 어느 쪽도 더 나아 보이게 서술하지 마라. 라벨의 길이·어조·구체성을 대칭으로 맞춰라.
3. imagine_prompt는 "그 선택을 한 6개월 뒤의 자신"을 상상하게 하는 문장이다.
   두 선택지의 문장 구조를 동일하게 하고 선택지 이름만 바꿔라.
4. speak_prompt는 **느낌**을 묻는 문장이다. 장단점·이유·근거를 묻지 마라.
   ("장단점을 설명해 주세요", "왜 그런지 말해주세요" 같은 문장은 금지다.)
   분석하듯 말하면 목소리가 평탄해져서 측정하려는 신호가 사라진다.
   좋은 예: "그 장면에서 든 느낌을 그대로 말해주세요."
   두 선택지가 동일한 구조여야 한다.
5. value_axis는 이 고민이 걸려 있는 가치 축이다. "A vs B" 형식의 짧은 구.
6. axis_side는 그 선택지가 value_axis의 **어느 극인지**다.
   반드시 value_axis에 쓴 두 낱말 중 하나를 그대로 써라.
   ("안정 vs 성장"이면 axis_side는 "안정" 또는 "성장"이다. 두 선택지가 서로 달라야 한다.)
7. 조언·평가·추천을 절대 넣지 마라.

JSON으로만 답하라:
{"title": "...", "value_axis": "안정 vs 성장",
 "options": [{"label": "...", "axis_side": "안정", "imagine_prompt": "...", "speak_prompt": "..."},
             {"label": "...", "axis_side": "성장", "imagine_prompt": "...", "speak_prompt": "..."}]}"""


def _axis_poles(value_axis: str) -> list[str]:
    """'안정 vs 성장' → ['안정', '성장']. 갈라내지 못하면 빈 목록."""
    for separator in (" vs ", " VS ", " 대 ", " / "):
        if separator in value_axis:
            poles = [p.strip() for p in value_axis.split(separator, 1)]
            if all(poles):
                return poles
    return []


def _normalize_axis_sides(decision: Decision) -> Decision:
    """axis_side가 value_axis의 실제 극과 맞는지 확인하고, 아니면 순서로 채운다.

    [8] 가치관 지도는 이 값으로만 집계된다. LLM이 빠뜨리거나 엉뚱한 낱말을 넣으면
    그 세션은 지도에서 통째로 빠지므로, 축을 갈라낼 수 있으면 순서로라도 채운다.
    """
    poles = _axis_poles(decision.value_axis)
    if len(poles) != len(decision.options):
        return decision

    valid = {p.lower() for p in poles}
    if all((o.axis_side or "").lower() in valid for o in decision.options) and len(
        {(o.axis_side or "").lower() for o in decision.options}
    ) == len(decision.options):
        return decision

    # options 배열의 순서가 곧 value_axis에 쓴 순서라고 본다.
    for option, pole in zip(decision.options, poles):
        option.axis_side = pole
    return decision


def _imagine_prompt(label: str) -> str:
    return f"'{label}'{josa(label, '을/를')} 선택한 6개월 뒤의 당신을 상상해보세요."


def _speak_prompt(_label: str) -> str:
    """★생각이 아니라 느낌을 묻는다.

    장단점을 따지게 하면 사용자가 이성적 분석 모드로 넘어간다. 그러면 음성이
    평탄해져서 우리가 재려던 신호 자체가 사라지고, 실패 모드 ①(근거 아웃소싱)을
    그대로 재생산한다. 직전 상상 구간이 이미 어느 선택지인지 말했으므로
    여기서 이름을 다시 부르지 않는다 — 두 선택지의 프롬프트가 완전히 같아진다.
    """
    return "방금 그 장면에서 든 느낌을 그대로 말해주세요."


def _fallback(raw_input: str) -> Decision:
    """LLM 없이도 파이프라인이 돌아야 한다. 'A vs B' / 'A 아니면 B' 정도만 갈라낸다."""
    text = raw_input.strip()
    labels: list[str] = []
    for separator in (" vs ", " VS ", " 아니면 ", " 또는 ", ", "):
        if separator in text:
            labels = [p.strip() for p in text.split(separator, 1)]
            break
    if len(labels) != 2 or not all(labels):
        labels = ["그렇게 한다", "하지 않는다"]

    return Decision(
        raw_input=raw_input,
        title=text[:60] or "고민",
        value_axis=f"{labels[0]} vs {labels[1]}",
        options=[
            Option(
                label=label,
                # 폴백에서는 축이 곧 선택지 이름이라 극도 같다.
                axis_side=label,
                imagine_prompt=_imagine_prompt(label),
                speak_prompt=_speak_prompt(label),
            )
            for label in labels
        ],
    )


def _randomize_order(decision: Decision) -> Decision:
    """제시 순서를 무작위로 정한다.

    뒤에 말한 쪽이 자연 안정화로 차분해 보이는 편향이 있다 (OPEN_QUESTIONS Q1).
    options 배열의 순서는 A/B 정체성이므로 건드리지 않고, order_index만 섞는다.
    """
    indices = list(range(len(decision.options)))
    random.shuffle(indices)
    for option, order in zip(decision.options, indices):
        option.order_index = order
    return decision


async def parse_decision(raw_input: str) -> Decision:
    parsed = await chat_json(_SYSTEM, raw_input)
    if not parsed or len(parsed.get("options", [])) != 2:
        return _randomize_order(_fallback(raw_input))

    try:
        options = [
            Option(
                label=o["label"],
                axis_side=(o.get("axis_side") or "").strip() or None,
                imagine_prompt=o.get("imagine_prompt") or _imagine_prompt(o["label"]),
                speak_prompt=o.get("speak_prompt") or _speak_prompt(o["label"]),
            )
            for o in parsed["options"]
        ]
        decision = Decision(
            raw_input=raw_input,
            title=parsed.get("title") or raw_input[:60],
            value_axis=parsed.get("value_axis") or "",
            options=options,
        )
    except (KeyError, TypeError):
        return _randomize_order(_fallback(raw_input))

    return _randomize_order(_normalize_axis_sides(decision))
