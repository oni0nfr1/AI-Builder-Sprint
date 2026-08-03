"""[3] 상대화 + [4] 판정.

⚠️ 이 모듈의 핵심은 **두 축의 분리**다.

    Δ(A, B)            →  선호   "어느 쪽에 마음이 가 있는가"
    (A,B) vs default   →  상태   "어떤 상태에서 이 기록을 남겼는가"

default는 선호 신호가 아니다. 선호는 오직 A와 B의 차이에서 나온다.
default는 그 차이를 어떤 조건에서 읽어야 하는지 알려주는 프레임이다.

고민 중이라는 건 A와 B 둘 다 긴장을 유발한다는 뜻이므로, default 없이
A↔B만 보면 "둘 다 당신을 긴장시킨다"는 가장 중요한 사실을 놓친다.

방향 해석(부호 테이블)은 직관_노트.pdf의 패턴 서술에 근거한 **규칙 기반 휴리스틱**이다.
계약을 지키는 한 통째로 학습 모델로 교체할 수 있다 (CLAUDE.md §4 교체 지점).
"""

from __future__ import annotations

from app.schemas.analysis import (
    BaselineSource,
    Delta,
    Lean,
    PreferenceDelta,
    PreferenceVerdict,
    StateDelta,
    StateLabel,
    StateVerdict,
    Verdict,
)
from app.schemas.capture import Phase, Segment
from app.schemas.common import HR_METRICS, MetricKey
from app.schemas.decision import Decision
from app.schemas.features import Features
from app.schemas.session import Session
from app.services import encoder
from app.services.korean import josa

# ─────────────────────────────────────────────────────────── 부호 테이블

ENGAGEMENT_SIGN: dict[MetricKey, float] = {
    # "음성 피치 상승 + 말속도 증가 → 몰입/진정성" (직관_노트.pdf)
    MetricKey.F0_MEAN: 1.0,
    MetricKey.F0_STD: 0.6,
    MetricKey.LOUDNESS_MEAN: 0.6,
    MetricKey.SPEECH_RATE: 0.8,
    MetricKey.PAUSE_RATIO: -0.6,  # 망설임
    # "음성 톤 하강 + 생체 저하 → 내적 충돌/불안"
    MetricKey.JITTER_LOCAL: -0.7,
    MetricKey.SHIMMER_LOCAL: -0.7,
    MetricKey.HNR: 0.7,  # 맑은 목소리 = 편안
}
"""선호 판정용. 양수 = 이 지표가 오르면 그쪽으로 기울었다고 본다."""

HR_ENGAGEMENT_SIGN: dict[MetricKey, float] = {
    MetricKey.BPM: -1.0,
}
"""심박은 별도 채널로 계산한다 — 음성과 반대 방향이면 `contradictory`가 된다.

심박 상승을 회피/긴장으로 읽는 것은 결정 맥락에서의 해석이다. 흥분으로도 오를 수
있어 본질적으로 모호하며, 그래서 단독으로 판정하지 않고 음성과 교차 검증한다.
"""

AROUSAL_SIGN: dict[MetricKey, float] = {
    MetricKey.BPM: 1.0,
    MetricKey.JITTER_LOCAL: 0.7,
    MetricKey.SHIMMER_LOCAL: 0.7,
    MetricKey.HNR: -0.7,
    MetricKey.SPEECH_RATE: 0.5,
    MetricKey.LOUDNESS_MEAN: 0.5,
    MetricKey.F0_MEAN: 0.5,
    MetricKey.PAUSE_RATIO: -0.3,
}
"""상태 판정용. 양수 = 이 지표가 오르면 각성으로 본다. F0_STD는 방향이 모호해 제외."""

# ─────────────────────────────────────────────────────────────── 임계값
# 실측 데이터를 보고 조정할 값들이다 (OPEN_QUESTIONS Q6).

PREFERENCE_THRESHOLD = 0.08
"""이보다 작으면 lean = none."""

AROUSAL_THRESHOLD = 0.10
"""이보다 크면 aroused, 음수로 이보다 크면 flat."""

CONTRADICTION_THRESHOLD = 0.08
"""음성과 심박이 각각 이 크기 이상으로 반대 방향일 때 contradictory."""

EXTREME_DELTA = 0.8
"""대칭 상대차가 이보다 크면 측정 조건 차이를 의심한다.

`_symmetric_ratio`의 최대 크기는 ±2다. 0.8이면 한쪽이 다른 쪽의 2.2배라는 뜻인데,
사람의 선호 차이가 한 세션 안에서 이만큼 벌어지기는 어렵다. 마이크와의 거리가
달랐거나 한쪽에서 거의 말하지 않았을 때 이렇게 된다.
(실측: loudness_mean -0.80, f0_std -1.10 이 동시에 나오고 pause_ratio 는 0.58이었다.)
"""

EXTREME_DELTA_COUNT = 2
"""이 개수 이상이면 두 녹음의 조건 자체가 달랐다고 보고 신뢰도를 깎는다."""

_EPSILON = 1e-9


# ══════════════════════════════════════════════════════ [3] 상대화


def _metrics_for(session: Session, segment: Segment, option_id: str | None) -> dict[MetricKey, float]:
    """한 구간(중립 / 선택지)의 지표를 모은다.

    심박은 imagine, 음성은 speak 구간에서 나오므로 둘을 합쳐야 한 구간의 전체 그림이 된다.
    신뢰도 미달 심박은 `Features.as_metrics()`가 이미 걸러낸다.
    """
    capture_ids = {
        c.id
        for c in session.captures
        if c.segment == segment and (option_id is None or c.option_id == option_id)
    }
    merged: dict[MetricKey, float] = {}
    for f in session.features:
        if f.capture_id in capture_ids:
            merged.update(f.as_metrics())
    return merged


def _symmetric_ratio(a: float, b: float) -> float:
    """대칭 상대차. (a - b) / mean(|a|, |b|)

    한쪽을 분모로 삼으면 A/B 순서를 바꿨을 때 크기가 달라진다. 선호는 대칭이어야 한다.
    """
    scale = (abs(a) + abs(b)) / 2.0
    return (a - b) / scale if scale > _EPSILON else 0.0


def compute_delta(session: Session, decision: Decision) -> Delta:
    """선호축과 상태축을 각각 계산한다."""
    option_a, option_b = decision.options[0], decision.options[1]

    metrics_a = _metrics_for(session, Segment.OPTION, option_a.id)
    metrics_b = _metrics_for(session, Segment.OPTION, option_b.id)
    default = _metrics_for(session, Segment.NEUTRAL, None)

    # 선호축 — A와 B의 차이. default는 여기 개입하지 않는다.
    preference_per_metric = {
        key: _symmetric_ratio(metrics_a[key], metrics_b[key])
        for key in metrics_a.keys() & metrics_b.keys()
    }

    # 상태축 — (A,B) 평균이 default에서 얼마나 벗어났나.
    state_per_metric: dict[MetricKey, float] = {}
    for key in (metrics_a.keys() & metrics_b.keys()) & default.keys():
        baseline = default[key]
        if abs(baseline) <= _EPSILON:
            continue
        current = (metrics_a[key] + metrics_b[key]) / 2.0
        state_per_metric[key] = (current - baseline) / abs(baseline)

    latent_preference, latent_state = _latent_distances(session, option_a.id, option_b.id)

    return Delta(
        session_id=session.id,
        baseline_source=BaselineSource.SESSION_NEUTRAL,
        preference=PreferenceDelta(
            option_a_id=option_a.id,
            option_b_id=option_b.id,
            per_metric=preference_per_metric,
            latent_distance=latent_preference,
        ),
        state=StateDelta(
            per_metric=state_per_metric,
            default_available=bool(default),
            latent_distance=latent_state,
        ),
    )


def _features_for(
    session: Session, segment: Segment, option_id: str | None
) -> Features | None:
    """한 구간의 **발화** 특징. 잠재벡터는 음성에서 나온다."""
    capture_ids = {
        c.id
        for c in session.captures
        if c.segment == segment
        and c.phase == Phase.SPEAK
        and (option_id is None or c.option_id == option_id)
    }
    for features in session.features:
        if features.capture_id in capture_ids and features.voice is not None:
            return features
    return None


def _latent_distances(
    session: Session, option_a_id: str, option_b_id: str
) -> tuple[float | None, float | None]:
    """잠재공간에서의 선호·상태 거리.

    ★크기만 나온다. 방향(어느 쪽 선호인가)은 라벨이 있어야 나온다 —
    지금은 규칙 기반 부호표가 그 역할을 한다 (OPEN_QUESTIONS Q8).

    표준화에 쓸 말뭉치가 부족하면 통째로 None 을 돌려준다. 근거 없는 거리를
    내놓느니 없다고 하는 편이 낫다.
    """
    keys = encoder.egemaps_keys()
    if not keys:
        return None, None
    # 개인별 표준화 — 남의 분포로 재면 그 사람 고유의 변동이 아니라 사람 간 차이를 잰다.
    stats = encoder.corpus_stats(keys, user_id=session.user_id)
    if stats is None:
        return None, None

    def vector(segment: Segment, option_id: str | None):
        features = _features_for(session, segment, option_id)
        return encoder.latent(features, keys, stats) if features else None

    z_a = vector(Segment.OPTION, option_a_id)
    z_b = vector(Segment.OPTION, option_b_id)
    z_default = vector(Segment.NEUTRAL, None)

    preference = encoder.cosine_distance(z_a, z_b) if z_a is not None and z_b is not None else None
    state = None
    if z_a is not None and z_b is not None and z_default is not None:
        state = encoder.cosine_distance((z_a + z_b) / 2.0, z_default)
    return preference, state


# ══════════════════════════════════════════════════════ [4] 판정


def _weighted_score(
    deltas: dict[MetricKey, float], signs: dict[MetricKey, float]
) -> tuple[float, dict[MetricKey, float]]:
    """부호 테이블을 적용한 가중 평균과 지표별 기여도를 함께 반환한다."""
    contributions: dict[MetricKey, float] = {}
    total_weight = 0.0
    for key, weight in signs.items():
        if key not in deltas:
            continue
        contributions[key] = round(weight * deltas[key], 4)
        total_weight += abs(weight)
    if total_weight <= _EPSILON:
        return 0.0, contributions
    return sum(contributions.values()) / total_weight, contributions


def _looks_like_condition_mismatch(per_metric: dict[MetricKey, float]) -> bool:
    """여러 지표가 동시에 극단으로 벌어졌는가.

    하나쯤 크게 튀는 건 진짜 신호일 수 있다. 여러 개가 한꺼번에 극단이면
    두 녹음의 조건 자체가 달랐다고 보는 편이 자연스럽다.
    """
    extreme = sum(1 for value in per_metric.values() if abs(value) >= EXTREME_DELTA)
    return extreme >= EXTREME_DELTA_COUNT


def _judge_state(delta: Delta) -> StateVerdict:
    if not delta.state.default_available or not delta.state.per_metric:
        return StateVerdict(label=StateLabel.UNKNOWN, magnitude=0.0)

    arousal, _ = _weighted_score(delta.state.per_metric, AROUSAL_SIGN)
    magnitude = min(abs(arousal), 1.0)

    if arousal > AROUSAL_THRESHOLD:
        label = StateLabel.AROUSED
    elif arousal < -AROUSAL_THRESHOLD:
        label = StateLabel.FLAT
    else:
        label = StateLabel.CALM
    return StateVerdict(label=label, magnitude=round(magnitude, 3))


def _judge_preference(
    delta: Delta, decision: Decision, state: StateVerdict
) -> PreferenceVerdict:
    per_metric = delta.preference.per_metric

    voice_score, voice_contrib = _weighted_score(per_metric, ENGAGEMENT_SIGN)
    hr_score, hr_contrib = _weighted_score(per_metric, HR_ENGAGEMENT_SIGN)

    contributing = {**voice_contrib, **hr_contrib}
    has_voice = bool(voice_contrib)
    has_hr = bool(hr_contrib)

    # 음성과 심박이 서로 반대 방향을 가리키면 그 자체가 판정 결과다.
    if (
        has_voice
        and has_hr
        and abs(voice_score) >= CONTRADICTION_THRESHOLD
        and abs(hr_score) >= CONTRADICTION_THRESHOLD
        and voice_score * hr_score < 0
    ):
        return PreferenceVerdict(
            lean=Lean.CONTRADICTORY,
            lean_option_id=None,
            magnitude=round(min(abs(voice_score - hr_score) / 2.0, 1.0), 3),
            confidence=0.0,
            contributing=contributing,
        )

    scores = [s for s, present in ((voice_score, has_voice), (hr_score, has_hr)) if present]
    combined = sum(scores) / len(scores) if scores else 0.0
    magnitude = min(abs(combined), 1.0)

    if magnitude < PREFERENCE_THRESHOLD:
        return PreferenceVerdict(
            lean=Lean.NONE,
            lean_option_id=None,
            magnitude=round(magnitude, 3),
            confidence=0.0,
            contributing=contributing,
        )

    lean = Lean.A if combined > 0 else Lean.B
    lean_option = decision.options[0] if lean is Lean.A else decision.options[1]

    # 신뢰도: 신호 크기에서 출발해, 각성 상태와 단일 채널 의존을 벌점으로 깎는다.
    confidence = min(magnitude / (PREFERENCE_THRESHOLD * 4), 1.0)
    if state.label is StateLabel.AROUSED:
        # 각성 상태에서의 선호 신호는 덜 믿을 만하다 — 둘 다 긴장시키는 고민이다.
        confidence *= 1.0 - min(state.magnitude, 0.6)
    if state.label is StateLabel.UNKNOWN:
        confidence *= 0.6
    if not (has_voice and has_hr):
        confidence *= 0.75
    if _looks_like_condition_mismatch(per_metric):
        # 선호가 아니라 녹음 조건이 달랐을 가능성이 크다. 판정은 유지하되 덜 믿는다.
        confidence *= 0.6

    return PreferenceVerdict(
        lean=lean,
        lean_option_id=lean_option.id,
        magnitude=round(magnitude, 3),
        confidence=round(confidence, 3),
        contributing=contributing,
    )


def _order_note(decision: Decision) -> str | None:
    """순서 효과 고지 (OPEN_QUESTIONS Q1).

    뒤에 말한 쪽이 자연 안정화로 차분해 보이는 편향이 있으므로 순서를 밝힌다.
    """
    ordered = sorted(decision.options, key=lambda o: o.order_index)
    if len(ordered) < 2:
        return None
    label = ordered[0].label
    return f"'{label}'{josa(label, '을/를')} 먼저 말씀하셨어요."


def _excluded_metrics(delta: Delta) -> list[MetricKey]:
    """신뢰도 미달 등으로 선호축에서 빠진 지표."""
    return [key for key in HR_METRICS if key not in delta.preference.per_metric]


def judge(delta: Delta, decision: Decision) -> Verdict:
    """두 축을 독립적으로 판정한 뒤, 상태로 선호의 신뢰도만 보정한다.

    반환값은 **내부 판정**이다. [5] 리포트에서 LLM 입력으로만 쓰이고,
    사용자에게 직접 노출되지 않는다.
    """
    state = _judge_state(delta)
    preference = _judge_preference(delta, decision, state)
    return Verdict(
        session_id=delta.session_id,
        preference=preference,
        state=state,
        order_note=_order_note(decision),
        excluded_metrics=_excluded_metrics(delta),
    )
