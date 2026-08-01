"""[3] 상대화 + [4] 판정 — Delta / Verdict.

⚠️ 이 파일의 핵심은 **두 축의 분리**다. 절대 섞지 말 것.

    Δ(A, B)            →  선호   "어느 쪽에 마음이 가 있는가"
    (A,B) vs default   →  상태   "지금 이 사람은 어떤 상태에서 이 기록을 남겼는가"

`default`는 선호 신호가 **아니다**. 선호는 오직 A와 B의 차이에서 나온다.
`default`는 그 차이를 어떤 조건에서 읽어야 하는지 알려주는 **프레임**이다.

고민 중이라는 건 A와 B 둘 다 긴장을 유발한다는 뜻이므로, default 없이
A↔B만 보면 노이즈를 신호로 오독한다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.common import MetricKey


class BaselineSource(StrEnum):
    """default를 어디서 얻었는가. [3] 단계만 갈아끼우면 이행 가능하다 (OPEN_QUESTIONS Q4)."""

    SESSION_NEUTRAL = "session_neutral"
    """세션 시작 20초 중립 앵커. MVP."""

    ACCUMULATED = "accumulated"
    """지금까지 중립 앵커들의 평균. 세션이 쌓이면."""

    CONTINUOUS_WEARABLE = "continuous_wearable"
    """웨어러블 지속 수집. 궁극 해법."""


class PreferenceDelta(BaseModel):
    """선호축 — Δ(A, B). 이것만이 선호 신호다."""

    option_a_id: str
    option_b_id: str
    per_metric: dict[MetricKey, float] = Field(default_factory=dict)
    """B 대비 A의 상대차(비율). 부호 있음."""


class StateDelta(BaseModel):
    """상태축 — (A,B) 평균 vs default. 선호가 아니라 해석 프레임이다."""

    per_metric: dict[MetricKey, float] = Field(default_factory=dict)
    default_available: bool = False
    """False면 상태 판정은 UNKNOWN."""


class Delta(BaseModel):
    session_id: str
    baseline_source: BaselineSource = BaselineSource.SESSION_NEUTRAL
    preference: PreferenceDelta
    state: StateDelta


class Lean(StrEnum):
    A = "A"
    B = "B"
    NONE = "none"
    """차이 미미 — 진짜 팽팽하거나 아직 안 익은 고민."""

    CONTRADICTORY = "contradictory"
    """음성과 심박이 서로 반대 방향."""


class StateLabel(StrEnum):
    CALM = "calm"
    """평소 수준 — 선호 신호 신뢰도 높음."""

    AROUSED = "aroused"
    """전반적 각성/긴장 — 이 고민 자체가 무겁다."""

    FLAT = "flat"
    """평소보다 전반적으로 낮음 — 피로/무기력/체념."""

    UNKNOWN = "unknown"


class PreferenceVerdict(BaseModel):
    lean: Lean
    lean_option_id: str | None = None
    magnitude: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    """상태가 AROUSED면 낮춘다 — 각성 상태에서의 선호 신호는 덜 믿을 만하다."""

    contributing: dict[MetricKey, float] = Field(default_factory=dict)
    """어떤 지표가 판정에 얼마나 기여했나."""


class StateVerdict(BaseModel):
    label: StateLabel = StateLabel.UNKNOWN
    magnitude: float = Field(default=0.0, ge=0.0, le=1.0)


class Verdict(BaseModel):
    """내부 판정. **사용자에게 직접 노출하지 않는다.**

    [5] 리포트 단계에서 LLM에 입력으로 들어가지만, LLM은 `lean`을 절대 발화하지 않는다.
    대신 그 방향으로 주의를 이끄는 질문을 만든다 (비대칭 질문 원칙).
    """

    session_id: str
    preference: PreferenceVerdict
    state: StateVerdict

    order_note: str | None = None
    """순서 효과 고지 (OPEN_QUESTIONS Q1). 예: "A를 먼저 말씀하셨어요"."""

    excluded_metrics: list[MetricKey] = Field(default_factory=list)
    """신뢰도 미달로 제외된 지표. 예: rPPG confidence < 0.4 인 경우의 bpm."""
