"""[0] 고민 등록 — 한 문장에서 선택지·가치축·프롬프트를 뽑는다.

⚠️ 두 선택지의 상상/발화 프롬프트는 **구조적으로 대칭**이어야 한다.
어느 한쪽에 권하는 뉘앙스가 섞이면 [5] 리포트에 도달하기 전에 이미 유도가 일어나고,
그 시점부터 우리가 재는 건 사용자의 직관이 아니라 우리 프롬프트의 효과다.
"""

from __future__ import annotations

import random
from collections import Counter
from difflib import SequenceMatcher

from app.core import storage
from app.schemas.decision import Decision, Option
from app.services.korean import josa
from app.services.llm import chat_json

_SYSTEM = """당신은 사용자의 고민 한 문장을 구조화하는 파서다.

반드시 지킬 것:
1. 선택지는 정확히 2개. 사용자가 실제로 저울질하는 것이어야 한다.
2. 두 선택지 중 어느 쪽도 더 나아 보이게 서술하지 마라. 라벨의 길이·어조·구체성을 대칭으로 맞춰라.
3. imagine_prompt는 **장면을 지정하되 그 장면의 성질은 비워두는** 문장이다.
   형식: "<시점> <그 선택을 한 장면>을 떠올려보세요. 무엇이 보이고 무엇이 느껴지나요?"

   ★시점은 고민의 무게에 맞춰라. 고정된 기간을 쓰지 마라.
     "점심 뭐 먹지" → "김치찌개를 먹고 있는 순간을"
     "이 기능 지금 할까" → "다음 주 그 기능이 올라간 화면을 보고 있는 자신을"
     "이직할까" → "6개월 뒤 새 회사에서 일하고 있는 자신을"
   작은 고민에 "6개월 뒤"를 붙이면 상상 자체가 되지 않아 측정이 무의미해진다.

   ★★그 장면이 **어떤 느낌인지는 절대 쓰지 마라.**
     ✗ "따뜻한 물줄기를 맞으며 피로가 풀리는 순간"   ← 감각과 결과를 우리가 정해줬다
     ✗ "뿌듯하게 결과물을 완성해 가는 순간"          ← 유인가가 섞였다
     ⭕ "샤워를 하고 있는 순간을 떠올려보세요. 무엇이 보이고 무엇이 느껴지나요?"
   느낌은 사용자가 채운다. 우리가 채우면 재는 것이 사용자의 직관이 아니라
   우리 문장의 효과가 된다.

   ★★★두 선택지의 문장은 **선택지를 가리키는 부분만 다르고 나머지는 글자까지 같아야**
   한다. 한쪽이 더 길거나 더 생생하면 그 자체가 유도다.
4. speak_prompt는 **느낌**을 묻는 문장이다. 장단점·이유·근거를 묻지 마라.
   ("장단점을 설명해 주세요", "왜 그런지 말해주세요" 같은 문장은 금지다.)
   분석하듯 말하면 목소리가 평탄해져서 측정하려는 신호가 사라진다.
   좋은 예: "그 장면에서 든 느낌을 그대로 말해주세요."
   두 선택지가 동일한 구조여야 한다.
5. value_axis는 이 고민이 걸려 있는 가치 축이다. "A vs B" 형식의 짧은 구.
   ★이미 쓰인 축 목록을 함께 준다. 뜻이 같은 축이 있으면 **그 문자열을 그대로 써라.**
   표현만 다른 축이 계속 생기면 고민들을 가로지르는 패턴이 영영 보이지 않는다.
6. axis_side는 그 선택지가 value_axis의 **어느 극인지**다.
   반드시 value_axis에 쓴 두 낱말 중 하나를 그대로 써라.
   ("안정 vs 성장"이면 axis_side는 "안정" 또는 "성장"이다. 두 선택지가 서로 달라야 한다.)
7. 조언·평가·추천을 절대 넣지 마라.

JSON으로만 답하라:
{"title": "...", "value_axis": "안정 vs 성장",
 "options": [{"label": "...", "axis_side": "안정", "imagine_prompt": "...", "speak_prompt": "..."},
             {"label": "...", "axis_side": "성장", "imagine_prompt": "...", "speak_prompt": "..."}]}"""


_VALENCE_WORDS = (
    # 쾌 — 한쪽만 이렇게 쓰이면 그쪽으로 기울게 만든다
    "따뜻", "포근", "편안", "상쾌", "개운", "여유로", "설레", "뿌듯", "보람",
    "성취감", "즐거", "행복", "홀가분", "후련", "만족스", "풀리", "해소",
    # 불쾌
    "지치", "힘들", "괴로", "답답", "불안", "초조", "후회", "아쉬", "막막",
)
"""장면의 성질을 우리가 정해버리는 말들. 상상 프롬프트에 들어가면 안 된다."""

_MIN_PROMPT_SIMILARITY = 0.55
"""두 상상 프롬프트가 이보다 덜 닮았으면 구조가 어긋난 것으로 본다."""


def _prompts_are_neutral(options: list[Option]) -> bool:
    """상상 프롬프트가 대칭이고 유인가가 없는가.

    ★어느 한쪽에 권하는 뉘앙스가 섞이면 [5] 리포트에 도달하기 전에 이미 유도가
    일어나고, 그 시점부터 우리가 재는 건 사용자의 직관이 아니라 우리 프롬프트의
    효과다 (CLAUDE.md). 프롬프트로만 막으면 샌다 — 실제로 이런 게 나갔다:

        "따뜻한 물줄기를 맞으며 피로가 풀리는 순간"     ← 감각과 결과를 우리가 정했다
        "작업 흐름을 유지하며 결과물을 완성해 가는 순간"  ← 결이 다르고 훨씬 건조하다
    """
    prompts = [o.imagine_prompt for o in options]
    if any(not p.strip() for p in prompts):
        return False
    if any(word in p for p in prompts for word in _VALENCE_WORDS):
        return False
    if len(prompts) != 2:
        return True
    similarity = SequenceMatcher(None, prompts[0], prompts[1]).ratio()
    return similarity >= _MIN_PROMPT_SIMILARITY


def _normalize_prompts(decision: Decision) -> Decision:
    """검증에 걸리면 두 프롬프트를 **함께** 규칙 기반으로 되돌린다.

    한쪽만 고치면 비대칭이 그대로 남으므로 반드시 둘 다 바꾼다.
    """
    if not _prompts_are_neutral(decision.options):
        for option in decision.options:
            option.imagine_prompt = _imagine_prompt(option.label)
    # 발화 프롬프트는 애초에 선택지 이름을 부르지 않아 항상 동일하다.
    for option in decision.options:
        option.speak_prompt = option.speak_prompt.strip() or _speak_prompt(option.label)
    return decision


def _axis_poles(value_axis: str) -> list[str]:
    """'안정 vs 성장' → ['안정', '성장']. 갈라내지 못하면 빈 목록."""
    for separator in (" vs ", " VS ", " 대 ", " / "):
        if separator in value_axis:
            poles = [p.strip() for p in value_axis.split(separator, 1)]
            if all(poles):
                return poles
    return []


# ═══════════════════════════════════════════ 축 통합
#
# ★[8] 가치관 지도는 value_axis **문자열**로 묶는다. 표현이 조금만 달라도 갈린다.
# 실측: 고민 25건에서 축이 9개로 쪼개졌고 그중 최소 세 쌍이 사실상 같은 축이었다
#       ("안정 vs 성장" / "안정 vs 변화" / "익숙함 vs 새로움",
#        "당장 vs 나중" / "즉시 vs 유예")
# 이러면 새 고민마다 새 축이 1회로 남아 "반복 → 가치관"이 구조적으로 성립하지 않는다.
#
# 두 겹으로 막는다.
#   (1) 결정적 — 극 집합이 같으면 기존 표기로 통일한다 ('성장 vs 안정' = '안정 vs 성장')
#   (2) LLM   — 기존 축 목록을 보여주고 뜻이 같으면 그대로 쓰게 한다

_MAX_KNOWN_AXES = 12
"""프롬프트에 넣을 기존 축 개수. 너무 많으면 억지로 끼워맞추게 된다."""


def _known_axes(user_id: str) -> list[str]:
    """그 사람이 지금까지 쓴 축을 많이 쓰인 순으로.

    남의 축을 보여주면 그 사람이 무엇을 고민 중인지가 새어 나간다.
    """
    counts: Counter[str] = Counter()
    for raw in storage.list_all("decisions", user_id=user_id):
        axis = (raw.get("value_axis") or "").strip()
        if axis:
            counts[axis] += 1
    return [axis for axis, _ in counts.most_common(_MAX_KNOWN_AXES)]


def _poles_key(value_axis: str) -> frozenset[str] | None:
    """축을 순서·대소문자와 무관한 열쇠로. 갈라내지 못하면 None."""
    poles = _axis_poles(value_axis)
    if len(poles) != 2:
        return None
    return frozenset(p.lower() for p in poles)


def _canonical_axis(value_axis: str, known: list[str]) -> str:
    """극 집합이 같은 기존 축이 있으면 그 표기로 통일한다.

    LLM 이 '성장 vs 안정'이라고 뒤집어 쓰는 것만으로 축이 갈리는 건 막을 수 있다.
    뜻이 같지만 낱말이 다른 경우(성장 vs 변화)는 여기서 못 잡고 LLM 쪽에 맡긴다.
    """
    key = _poles_key(value_axis)
    if key is None:
        return value_axis
    for candidate in known:
        if _poles_key(candidate) == key:
            return candidate
    return value_axis


def _user_message(raw_input: str, known: list[str]) -> str:
    if not known:
        return raw_input
    listed = "\n".join(f"- {axis}" for axis in known)
    return (
        f"{raw_input}\n\n"
        f"[참고 — 다른 고민에서 쓰인 축]\n{listed}\n\n"
        "이 목록은 참고일 뿐이다. **이 고민의 축을 먼저 스스로 정하라.**\n"
        "그렇게 정한 축이 목록의 어떤 축과 **거의 같은 뜻**일 때만 그 표기를 그대로 쓴다.\n"
        "조금이라도 다르면 새 축을 만들어라. 목록에 없는 축이 나오는 것이 정상이고, "
        "대부분의 고민은 새 축을 갖는다. 억지로 끼워맞추면 없는 가치관을 만들어내는 것이다.\n"
        "예: '부모님께 사실대로 말할지' 는 '관계 vs 자율' 이 아니라 '정직 vs 배려' 다."
    )


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
    """★시점을 못 박지 않고, 느낌도 우리가 채우지 않는다.

    "6개월 뒤"로 고정했더니 "점심 뭐 먹지" 같은 작은 고민에서 상상 자체가
    되지 않았다. 그러면 상상 구간 15초가 빈 채로 지나가고 심박 측정이 무의미해진다.

    동시에 장면의 **성질**은 비워둔다. "따뜻한 물줄기를 맞으며 피로가 풀리는"처럼
    쓰면 사용자는 자기 상상이 아니라 우리 시나리오를 떠올리게 되고, 그때 재는 것은
    사용자의 직관이 아니라 우리 문장의 효과다. 그래서 장면만 가리키고 감각은
    질문으로 넘긴다 — 상상은 자극하되 내용은 사용자가 채운다.
    """
    return (
        f"'{label}'{josa(label, '을/를')} 선택한 뒤의 한 장면을 떠올려보세요. "
        "무엇이 보이고 무엇이 느껴지나요?"
    )


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


def _finalize(decision: Decision, known: list[str]) -> Decision:
    """축 통합 → 극 배정 → 프롬프트 검증 → 순서 랜덤화.

    축 통합이 가장 먼저다. 표기가 바뀌면 그에 맞춰 극을 배정해야 하기 때문이다.
    """
    decision.value_axis = _canonical_axis(decision.value_axis, known)
    return _randomize_order(_normalize_prompts(_normalize_axis_sides(decision)))


async def parse_decision(raw_input: str, user_id: str = "local") -> Decision:
    known = _known_axes(user_id)
    parsed = await chat_json(_SYSTEM, _user_message(raw_input, known))
    if not parsed or len(parsed.get("options", [])) != 2:
        return _finalize(_fallback(raw_input), known)

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
        return _finalize(_fallback(raw_input), known)

    return _finalize(decision, known)
