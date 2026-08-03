"""파이프라인 계약. 정의는 `docs/CONTRACTS.md`가 단일 진실 소스."""

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
from app.schemas.capture import Capture, Phase, RgbSample, RppgMeasurement, Segment
from app.schemas.common import (
    HR_METRICS,
    VOICE_METRICS,
    ApiError,
    ApiResponse,
    MetricDelta,
    MetricKey,
)
from app.schemas.decision import Decision, DecisionCreateRequest, Option
from app.schemas.features import (
    CONFIDENCE_FLOOR,
    Features,
    HeartRateFeatures,
    VoiceFeatures,
)
from app.schemas.report import DEFAULT_BODY_TAGS, Annotation, Report
from app.schemas.session import (
    Horizon,
    Conviction,
    ConvictionGroup,
    Retrospective,
    Session,
    ValueAxisEntry,
    ValueMap,
)

__all__ = [
    # common
    "MetricKey",
    "MetricDelta",
    "ApiResponse",
    "ApiError",
    "VOICE_METRICS",
    "HR_METRICS",
    # [0]
    "Decision",
    "Option",
    "DecisionCreateRequest",
    # [1]
    "Capture",
    "RgbSample",
    "RppgMeasurement",
    "Segment",
    "Phase",
    # [2]
    "Features",
    "VoiceFeatures",
    "HeartRateFeatures",
    "CONFIDENCE_FLOOR",
    # [3][4]
    "Delta",
    "PreferenceDelta",
    "StateDelta",
    "BaselineSource",
    "Verdict",
    "PreferenceVerdict",
    "StateVerdict",
    "Lean",
    "StateLabel",
    # [5][6]
    "Report",
    "Annotation",
    "DEFAULT_BODY_TAGS",
    # [7][8]
    "Session",
    "Conviction",
    "ConvictionGroup",
    "Retrospective",
    "Horizon",
    "ValueMap",
    "ValueAxisEntry",
]
