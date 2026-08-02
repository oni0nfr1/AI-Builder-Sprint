"""[2] 특징 추출 디스패치.

심박은 imagine(정지), 음성은 speak 구간에서 나온다.
"""

from __future__ import annotations

from app.schemas.capture import Capture, Phase
from app.schemas.features import Features, HeartRateFeatures
from app.services.rppg import estimate_heart_rate
from app.services.voice import extract_voice_features


def extract(capture: Capture) -> Features:
    if capture.phase is Phase.IMAGINE:
        measurement = capture.rppg_measurement
        if measurement is not None:
            return Features(
                capture_id=capture.id,
                hr=HeartRateFeatures(
                    bpm=measurement.bpm,
                    confidence=measurement.confidence,
                    source="rppg-web",
                    signal_quality=measurement.signal_quality,
                    agreement=measurement.agreement,
                    reason_codes=measurement.reason_codes,
                ),
            )
        if capture.rgb_series is None:
            # rPPG가 준비되지 않은 캡처는 심박 축만 비운다.
            return Features(capture_id=capture.id)
        return Features(
            capture_id=capture.id,
            hr=estimate_heart_rate(capture.rgb_series, capture.fps),
        )
    return Features(
        capture_id=capture.id,
        voice=extract_voice_features(capture.audio_base64),
    )
