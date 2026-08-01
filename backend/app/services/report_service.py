"""[5] 메타인지 리포트 — 산파술.

우리는 내부적으로 판정한다(`Verdict`). 하지만 **그걸 발화하지 않는다.**
대신 그 방향으로 주의를 이끄는 질문을 만들어 사용자가 스스로 결론에 도달하게 한다.

    유도는 관찰이 아니라 질문에서 일어난다.
    observations는 데이터 번역일 뿐이고, tagging_question의 *방향*이
    우리가 쥔 유일한 핸들이다. — 비대칭 질문 원칙

금지 (어기면 제품이 성립하지 않는다):
    ✗ 어느 쪽이 낫다/맞다              → 결정 대행
    ✗ 감정 라벨 단정 ("불안하시군요")   → 결정 대행과 동일
    ✗ 원인 추정 ("~때문에")
    ✗ 조언·제안·격려
"""

from __future__ import annotations

from app.schemas.analysis import Delta, Lean, StateLabel, Verdict
from app.schemas.common import MetricKey
from app.schemas.decision import Decision
from app.schemas.report import DEFAULT_BODY_TAGS, Report
from app.schemas.session import Session
from app.services.llm import chat_json

_METRIC_LABEL: dict[MetricKey, str] = {
    MetricKey.F0_MEAN: "목소리 높이",
    MetricKey.F0_STD: "억양 변화",
    MetricKey.LOUDNESS_MEAN: "목소리 크기",
    MetricKey.JITTER_LOCAL: "목소리 떨림",
    MetricKey.SHIMMER_LOCAL: "목소리 흔들림",
    MetricKey.HNR: "목소리 맑기",
    MetricKey.SPEECH_RATE: "말속도",
    MetricKey.PAUSE_RATIO: "말 사이 쉼",
    MetricKey.BPM: "심박수",
}

_MAX_OBSERVATIONS = 4
_MIN_REPORTABLE_DELTA = 0.05

_SELF_STATEMENT = "지금은 어느 쪽에 마음이 더 가 있는 것 같으세요?"

_SYSTEM = """당신은 '직관 노트'의 메타인지 거울이다. 사용자가 스스로를 관찰하도록 돕는다.

당신은 내부 판정 결과를 받지만, **그것을 절대 발화하지 않는다.**
대신 그 방향으로 사용자의 주의를 이끄는 질문을 만든다. 결론은 사용자가 낸다.

절대 금지:
- 어느 쪽이 낫다/맞다/추천한다는 표현
- 감정이나 상태를 단정하는 라벨 ("불안하시군요", "확신이 있으시네요")
- 원인 추정 ("~때문에 긴장하신 것 같아요")
- 조언, 제안, 격려, 위로

해야 할 것:
- observations: 측정된 변화를 사용자의 일상 언어로 번역해 사실만 서술한다.
  각 문장은 "A를 말할 때 ~했고, B를 말할 때 ~했어요" 형태의 비교여야 한다.
- tagging_question: 신호가 강한 쪽을 향하는 질문 하나. "그때 몸에서 뭐가 느껴지셨어요?" 계열.
  어느 쪽을 물을지가 유일한 유도 수단이다. 질문 자체에 판단을 담지 마라.
- state_note: 지금 어떤 상태에서 이 기록을 남겼는지 알리는 한 문장. 판단이 아니라 조건 고지다.

JSON으로만 답하라:
{"state_note": "...", "observations": ["...", "..."], "tagging_question": "..."}"""


def _label_of(decision: Decision, option_id: str | None) -> str:
    for option in decision.options:
        if option.id == option_id:
            return option.label
    return "그 선택지"


def _state_note(verdict: Verdict) -> str:
    """① 상태 고지. 프레임이므로 가장 먼저 나온다.

    이게 있어야 사용자가 이번 기록을 얼마나 믿을지 스스로 판단할 수 있고,
    그 판단 자체가 메타인지 훈련이다.
    """
    match verdict.state.label:
        case StateLabel.AROUSED:
            return (
                "오늘은 평소보다 전반적으로 신호가 올라가 있는 상태에서 기록하셨어요. "
                "두 선택지 모두에서 그랬습니다."
            )
        case StateLabel.FLAT:
            return "오늘은 평소보다 전반적으로 신호가 가라앉은 상태에서 기록하셨어요."
        case StateLabel.CALM:
            return "오늘은 평소와 비슷한 상태에서 기록하셨어요."
        case _:
            return (
                "평소 상태 기준이 아직 없어서, 이번에는 두 선택지 사이의 차이만 보여드려요."
            )


def _observations(verdict: Verdict, decision: Decision) -> list[str]:
    """② 관찰만. 어느 쪽이 낫다는 말도, 감정 라벨도 붙이지 않는다."""
    label_a = decision.options[0].label
    label_b = decision.options[1].label

    ranked = sorted(
        (
            (key, value)
            for key, value in verdict.preference.contributing.items()
            if abs(value) >= _MIN_REPORTABLE_DELTA
        ),
        key=lambda item: abs(item[1]),
        reverse=True,
    )[:_MAX_OBSERVATIONS]

    if not ranked:
        return [
            f"'{label_a}'을(를) 말할 때와 '{label_b}'을(를) 말할 때, "
            "측정된 신호의 차이가 거의 없었어요."
        ]

    lines = []
    for key, value in ranked:
        metric = _METRIC_LABEL.get(key, key.value)
        higher, lower = (label_a, label_b) if value > 0 else (label_b, label_a)
        percent = round(abs(value) * 100)
        lines.append(
            f"'{higher}'을(를) 말할 때 {metric}이(가) "
            f"'{lower}'을(를) 말할 때보다 {percent}% 높았어요."
        )
    return lines


def _tagging_question(verdict: Verdict, decision: Decision) -> str:
    """③ 비대칭 질문 — 신호가 강한 쪽으로 향한다. 유도가 일어나는 유일한 지점."""
    match verdict.preference.lean:
        case Lean.A | Lean.B:
            label = _label_of(decision, verdict.preference.lean_option_id)
            return f"'{label}'을(를) 말할 때, 몸에서 뭐가 느껴지셨어요?"
        case Lean.CONTRADICTORY:
            return (
                "목소리와 심장이 서로 다른 방향을 가리켰어요. "
                "두 선택지를 말할 때 각각 몸에서 뭐가 느껴지셨는지 기억나세요?"
            )
        case _:
            return (
                "두 선택지에서 신호가 비슷하게 나왔어요. "
                "말할 때 몸에서 뭐가 느껴지셨는지 기억나세요?"
            )


def _tagging_option_id(verdict: Verdict) -> str | None:
    """태그를 귀속시킬 선택지. lean이 없으면 특정 선택지를 지목하지 않는다."""
    if verdict.preference.lean in (Lean.A, Lean.B):
        return verdict.preference.lean_option_id
    return None


def _fallback(verdict: Verdict, decision: Decision) -> Report:
    return Report(
        state_note=_state_note(verdict),
        observations=_observations(verdict, decision),
        tagging_question=_tagging_question(verdict, decision),
        tagging_option_id=_tagging_option_id(verdict),
        body_tag_options=DEFAULT_BODY_TAGS,
        self_statement_question=_SELF_STATEMENT,
    )


def _llm_input(verdict: Verdict, delta: Delta, decision: Decision, session: Session) -> str:
    """LLM에 넘기는 내부 상태. lean이 들어가지만 발화는 금지된다."""
    transcripts = [c.transcript for c in session.captures if c.transcript]
    measured = {
        _METRIC_LABEL.get(key, key.value): f"{value:+.1%}"
        for key, value in delta.preference.per_metric.items()
    }
    lean_label = (
        _label_of(decision, verdict.preference.lean_option_id)
        if verdict.preference.lean in (Lean.A, Lean.B)
        else "없음"
    )
    return (
        f"고민: {decision.title}\n"
        f"선택지 A: {decision.options[0].label}\n"
        f"선택지 B: {decision.options[1].label}\n"
        f"\n[내부 판정 — 절대 발화 금지]\n"
        f"기울어진 쪽: {lean_label} (신뢰도 {verdict.preference.confidence:.2f})\n"
        f"상태: {verdict.state.label.value}\n"
        f"\n[측정된 변화 — A 기준, B 대비]\n"
        + "\n".join(f"- {k}: {v}" for k, v in measured.items())
        + (f"\n\n[사용자 발화]\n" + "\n".join(transcripts) if transcripts else "")
        + f"\n\n주의: 신호가 강한 쪽은 '{lean_label}'이다. "
        "이 사실을 말하지 말고, 그쪽을 향한 질문으로만 주의를 이끌어라."
    )


async def build_report(
    verdict: Verdict, delta: Delta, decision: Decision, session: Session
) -> Report:
    """LLM이 있으면 표현을 다듬고, 없으면 규칙 기반으로도 동일한 구조를 만든다."""
    generated = await chat_json(_SYSTEM, _llm_input(verdict, delta, decision, session))
    if not generated:
        return _fallback(verdict, decision)

    observations = [str(o) for o in generated.get("observations", []) if str(o).strip()]
    return Report(
        state_note=str(generated.get("state_note") or _state_note(verdict)),
        observations=observations or _observations(verdict, decision),
        tagging_question=str(
            generated.get("tagging_question") or _tagging_question(verdict, decision)
        ),
        # LLM이 어느 선택지를 물었는지는 신뢰하지 않고 판정에서 직접 가져온다.
        tagging_option_id=_tagging_option_id(verdict),
        body_tag_options=DEFAULT_BODY_TAGS,
        # 자기 진술 질문은 LLM에 맡기지 않는다 — 표현이 흔들리면 유도가 섞인다.
        self_statement_question=_SELF_STATEMENT,
    )
