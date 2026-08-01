"""[3][4] 상대화·판정 검증.

가장 중요한 검증은 **두 축이 실제로 분리되어 있는가**다:
같은 Δ(A,B)라도 default가 달라지면 선호는 그대로이고 상태·신뢰도만 바뀌어야 한다.
"""

from __future__ import annotations

from app.schemas.analysis import Lean, StateLabel
from app.schemas.capture import Capture, Phase, Segment
from app.schemas.decision import Decision, Option
from app.schemas.features import Features, HeartRateFeatures, VoiceFeatures
from app.schemas.session import Session
from app.services.analysis_service import compute_delta, judge


def _voice(
    f0: float = 200.0,
    rate: float = 4.0,
    loudness: float = 60.0,
    jitter: float = 0.02,
    shimmer: float = 0.08,
    hnr: float = 15.0,
    pause: float = 0.2,
) -> VoiceFeatures:
    return VoiceFeatures(
        f0_mean=f0,
        f0_std=20.0,
        loudness_mean=loudness,
        jitter_local=jitter,
        shimmer_local=shimmer,
        hnr=hnr,
        speech_rate=rate,
        pause_ratio=pause,
    )


def _hr(bpm: float) -> HeartRateFeatures:
    return HeartRateFeatures(bpm=bpm, confidence=0.8, snr_db=8.0)


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


def _session(
    a_voice: VoiceFeatures,
    a_hr: HeartRateFeatures,
    b_voice: VoiceFeatures,
    b_hr: HeartRateFeatures,
    default_voice: VoiceFeatures | None = None,
    default_hr: HeartRateFeatures | None = None,
) -> Session:
    session = Session(decision_id="dec-1")
    plan = [
        (Segment.OPTION, "opt-a", Phase.SPEAK, a_voice, None),
        (Segment.OPTION, "opt-a", Phase.IMAGINE, None, a_hr),
        (Segment.OPTION, "opt-b", Phase.SPEAK, b_voice, None),
        (Segment.OPTION, "opt-b", Phase.IMAGINE, None, b_hr),
    ]
    if default_voice is not None:
        plan.append((Segment.NEUTRAL, None, Phase.SPEAK, default_voice, None))
    if default_hr is not None:
        plan.append((Segment.NEUTRAL, None, Phase.IMAGINE, None, default_hr))

    for segment, option_id, phase, voice, hr in plan:
        capture = Capture(session_id=session.id, segment=segment, option_id=option_id, phase=phase)
        session.captures.append(capture)
        session.features.append(Features(capture_id=capture.id, voice=voice, hr=hr))
    return session


def _analyze(session: Session, decision: Decision):
    delta = compute_delta(session, decision)
    return delta, judge(delta, decision)


# ────────────────────────────────────────────────────────── 선호축


def test_clear_lean_toward_a() -> None:
    """A에서 피치·말속도가 높고 심박은 낮다 → A쪽으로 기울었다고 본다."""
    decision = _decision()
    session = _session(
        a_voice=_voice(f0=230.0, rate=4.8, hnr=18.0, jitter=0.015),
        a_hr=_hr(70.0),
        b_voice=_voice(f0=180.0, rate=3.4, hnr=12.0, jitter=0.030),
        b_hr=_hr(84.0),
        default_voice=_voice(),
        default_hr=_hr(72.0),
    )
    _, verdict = _analyze(session, decision)
    assert verdict.preference.lean is Lean.A
    assert verdict.preference.lean_option_id == "opt-a"
    assert verdict.preference.confidence > 0.0


def test_no_lean_when_options_are_alike() -> None:
    decision = _decision()
    session = _session(
        a_voice=_voice(),
        a_hr=_hr(75.0),
        b_voice=_voice(),
        b_hr=_hr(75.0),
        default_voice=_voice(),
        default_hr=_hr(75.0),
    )
    _, verdict = _analyze(session, decision)
    assert verdict.preference.lean is Lean.NONE


def test_contradictory_when_voice_and_heart_disagree() -> None:
    """목소리는 A로, 심박은 B로 기운다 → 그 불일치 자체가 판정 결과다."""
    decision = _decision()
    session = _session(
        a_voice=_voice(f0=240.0, rate=5.0, hnr=19.0, jitter=0.012),
        a_hr=_hr(95.0),  # 심박은 A에서 훨씬 높다
        b_voice=_voice(f0=175.0, rate=3.2, hnr=11.0, jitter=0.032),
        b_hr=_hr(68.0),
        default_voice=_voice(),
        default_hr=_hr(72.0),
    )
    _, verdict = _analyze(session, decision)
    assert verdict.preference.lean is Lean.CONTRADICTORY
    assert verdict.preference.lean_option_id is None


def test_preference_is_symmetric() -> None:
    """A/B 순서를 바꿔도 기울기의 크기는 같아야 한다."""
    decision = _decision()
    forward = _session(
        a_voice=_voice(f0=230.0, rate=4.8),
        a_hr=_hr(70.0),
        b_voice=_voice(f0=180.0, rate=3.4),
        b_hr=_hr(84.0),
        default_voice=_voice(),
        default_hr=_hr(72.0),
    )
    swapped = _session(
        a_voice=_voice(f0=180.0, rate=3.4),
        a_hr=_hr(84.0),
        b_voice=_voice(f0=230.0, rate=4.8),
        b_hr=_hr(70.0),
        default_voice=_voice(),
        default_hr=_hr(72.0),
    )
    _, v1 = _analyze(forward, decision)
    _, v2 = _analyze(swapped, decision)
    assert v1.preference.lean is Lean.A
    assert v2.preference.lean is Lean.B
    assert v1.preference.magnitude == v2.preference.magnitude


# ────────────────────────────────────────────────────────── 상태축


def test_state_aroused_when_both_options_exceed_default() -> None:
    """A와 B 둘 다 평소보다 높다 → 각성 상태. 이건 선호가 아니라 상태 판정이다."""
    decision = _decision()
    session = _session(
        a_voice=_voice(f0=250.0, jitter=0.05, shimmer=0.16, hnr=9.0),
        a_hr=_hr(100.0),
        b_voice=_voice(f0=245.0, jitter=0.05, shimmer=0.16, hnr=9.0),
        b_hr=_hr(98.0),
        default_voice=_voice(f0=200.0, jitter=0.02, shimmer=0.08, hnr=15.0),
        default_hr=_hr(70.0),
    )
    _, verdict = _analyze(session, decision)
    assert verdict.state.label is StateLabel.AROUSED


def test_state_unknown_without_default() -> None:
    """중립 앵커가 없으면 상태를 판단할 수 없다."""
    decision = _decision()
    session = _session(
        a_voice=_voice(f0=230.0),
        a_hr=_hr(70.0),
        b_voice=_voice(f0=180.0),
        b_hr=_hr(84.0),
    )
    delta, verdict = _analyze(session, decision)
    assert delta.state.default_available is False
    assert verdict.state.label is StateLabel.UNKNOWN


def test_state_calm_when_close_to_default() -> None:
    decision = _decision()
    session = _session(
        a_voice=_voice(f0=205.0),
        a_hr=_hr(73.0),
        b_voice=_voice(f0=196.0),
        b_hr=_hr(71.0),
        default_voice=_voice(f0=200.0),
        default_hr=_hr(72.0),
    )
    _, verdict = _analyze(session, decision)
    assert verdict.state.label is StateLabel.CALM


# ──────────────────────────────────── ★ 두 축의 분리 (핵심 검증)


def test_same_preference_different_default_changes_only_state() -> None:
    """같은 Δ(A,B), 다른 default.

    → 선호(lean, magnitude)는 **그대로**여야 하고,
      상태와 그로 인한 confidence만 달라져야 한다.

    default가 선호 계산에 새어 들어가면 이 테스트가 깨진다.
    """
    decision = _decision()
    a_voice, a_hr = _voice(f0=230.0, rate=4.8, hnr=18.0), _hr(74.0)
    b_voice, b_hr = _voice(f0=180.0, rate=3.4, hnr=12.0), _hr(88.0)

    calm_session = _session(
        a_voice, a_hr, b_voice, b_hr,
        default_voice=_voice(f0=205.0, rate=4.1, hnr=15.0),
        default_hr=_hr(81.0),
    )
    aroused_session = _session(
        a_voice, a_hr, b_voice, b_hr,
        default_voice=_voice(f0=150.0, rate=3.0, hnr=20.0, jitter=0.008, shimmer=0.04),
        default_hr=_hr(58.0),
    )

    calm_delta, calm_verdict = _analyze(calm_session, decision)
    aroused_delta, aroused_verdict = _analyze(aroused_session, decision)

    # 선호축은 default와 무관하다
    assert calm_delta.preference.per_metric == aroused_delta.preference.per_metric
    assert calm_verdict.preference.lean == aroused_verdict.preference.lean
    assert calm_verdict.preference.magnitude == aroused_verdict.preference.magnitude

    # 상태축만 달라진다
    assert calm_verdict.state.label is StateLabel.CALM
    assert aroused_verdict.state.label is StateLabel.AROUSED

    # 각성 상태에서는 같은 선호 신호라도 신뢰도가 낮아진다
    assert aroused_verdict.preference.confidence < calm_verdict.preference.confidence


def test_low_confidence_heart_rate_is_excluded() -> None:
    """rPPG 신뢰도가 바닥이면 심박 축을 통째로 뺀다."""
    decision = _decision()
    session = _session(
        a_voice=_voice(f0=230.0),
        a_hr=HeartRateFeatures(bpm=70.0, confidence=0.1, snr_db=-4.0),
        b_voice=_voice(f0=180.0),
        b_hr=HeartRateFeatures(bpm=90.0, confidence=0.1, snr_db=-4.0),
        default_voice=_voice(),
        default_hr=_hr(72.0),
    )
    delta, verdict = _analyze(session, decision)
    from app.schemas.common import MetricKey

    assert MetricKey.BPM not in delta.preference.per_metric
    assert MetricKey.BPM in verdict.excluded_metrics


def test_order_note_reflects_presentation_order() -> None:
    decision = _decision()
    decision.options[0].order_index = 1
    decision.options[1].order_index = 0
    session = _session(_voice(), _hr(72.0), _voice(), _hr(72.0))
    _, verdict = _analyze(session, decision)
    assert verdict.order_note is not None
    assert "남는다" in verdict.order_note
