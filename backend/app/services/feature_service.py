"""[2] 특징 추출 디스패치.

심박은 imagine(정지), 음성은 speak 구간에서 나온다.
"""

from __future__ import annotations

from app.schemas.capture import Capture, Phase
from app.schemas.features import Features
from app.services.rppg import estimate_heart_rate
from app.services.voice import extract_voice_features


def extract(capture: Capture) -> Features:
    if capture.phase is Phase.IMAGINE:
        return Features(
            capture_id=capture.id,
            hr=estimate_heart_rate(capture.rgb_series, capture.fps),
        )
    return Features(
        capture_id=capture.id,
        voice=extract_voice_features(capture.audio_base64),
    )
