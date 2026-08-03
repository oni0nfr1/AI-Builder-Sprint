"""[2] 음성 특징 추출.

openSMILE eGeMAPS v02(88지표)를 1차 경로로 쓴다. eGeMAPS는 음성에서 감정과
자율신경계 상태를 측정하기 위해 음성학계가 정립한 표준이고, 우리가 노리는
jitter / shimmer / HNR을 포함한다.

Essentia(.js)로 대체할 수 없는 이유: Essentia는 MIR(음악 정보 검색) 중심이라
jitter / shimmer / HNR이 아예 없다 (OPEN_QUESTIONS Q2).

openSMILE이 실패하면 parselmouth(Praat)로 폴백한다. Praat이 이 지표들의 원조다.
"""

from __future__ import annotations

import base64
import io
import logging

import numpy as np
import soundfile as sf

from app.schemas.features import VoiceFeatures

logger = logging.getLogger(__name__)

_EGEMAPS_MAP = {
    "f0_mean": "F0semitoneFrom27.5Hz_sma3nz_amean",
    "f0_std": "F0semitoneFrom27.5Hz_sma3nz_stddevNorm",
    "loudness_mean": "loudness_sma3_amean",
    "jitter_local": "jitterLocal_sma3nz_amean",
    "shimmer_local": "shimmerLocaldB_sma3nz_amean",
    "hnr": "HNRdBACF_sma3nz_amean",
    "speech_rate": "VoicedSegmentsPerSec",
}

_smile = None


def _get_smile():
    """openSMILE 인스턴스는 초기화 비용이 있어 재사용한다."""
    global _smile
    if _smile is None:
        import opensmile

        _smile = opensmile.Smile(
            feature_set=opensmile.FeatureSet.eGeMAPSv02,
            feature_level=opensmile.FeatureLevel.Functionals,
        )
    return _smile


def decode_wav(audio_base64: str) -> tuple[np.ndarray, int]:
    """base64 WAV → (mono float32 신호, 샘플레이트).

    브라우저가 16-bit PCM WAV로 인코딩해 보낸다 (docs/CONTRACTS.md [1]).
    서버에 ffmpeg 같은 코덱 의존성을 만들지 않기 위한 계약이다.
    """
    raw = base64.b64decode(audio_base64)
    signal, sample_rate = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)
    return signal.mean(axis=1), int(sample_rate)


def _pause_ratio(egemaps: dict[str, float]) -> float:
    voiced = egemaps.get("MeanVoicedSegmentLengthSec", 0.0)
    unvoiced = egemaps.get("MeanUnvoicedSegmentLength", 0.0)
    total = voiced + unvoiced
    return float(unvoiced / total) if total > 1e-9 else 0.0


def _extract_with_opensmile(signal: np.ndarray, sample_rate: int) -> VoiceFeatures:
    frame = _get_smile().process_signal(signal, sample_rate)
    egemaps = {k: float(v) for k, v in frame.iloc[0].items()}

    values = {name: egemaps[key] for name, key in _EGEMAPS_MAP.items()}
    return VoiceFeatures(
        **values,
        pause_ratio=_pause_ratio(egemaps),
        egemaps=egemaps,
    )


def _extract_with_parselmouth(signal: np.ndarray, sample_rate: int) -> VoiceFeatures:
    """폴백 경로. Praat이 jitter/shimmer/HNR의 원조 구현이다."""
    import parselmouth
    from parselmouth.praat import call

    sound = parselmouth.Sound(signal.astype(np.float64), sampling_frequency=sample_rate)

    pitch = sound.to_pitch()
    f0_values = pitch.selected_array["frequency"]
    voiced = f0_values[f0_values > 0]

    point_process = call(sound, "To PointProcess (periodic, cc)", 75, 500)
    jitter = call(point_process, "Get jitter (local)", 0, 0, 1e-4, 0.02, 1.3)
    shimmer = call(
        [sound, point_process], "Get shimmer (local_dB)", 0, 0, 1e-4, 0.02, 1.3, 1.6
    )
    harmonicity = call(sound, "To Harmonicity (cc)", 0.01, 75, 0.1, 1.0)
    hnr = call(harmonicity, "Get mean", 0, 0)

    duration = len(signal) / sample_rate
    voiced_ratio = float(len(voiced) / len(f0_values)) if len(f0_values) else 0.0

    def _finite(x: float, fallback: float = 0.0) -> float:
        return float(x) if np.isfinite(x) else fallback

    return VoiceFeatures(
        f0_mean=float(np.mean(voiced)) if voiced.size else 0.0,
        f0_std=float(np.std(voiced) / np.mean(voiced)) if voiced.size and np.mean(voiced) > 0 else 0.0,
        loudness_mean=float(np.sqrt(np.mean(signal**2))),
        jitter_local=_finite(jitter),
        shimmer_local=_finite(shimmer),
        hnr=_finite(hnr),
        speech_rate=voiced_ratio / duration * len(voiced) / max(len(f0_values), 1) if duration > 0 else 0.0,
        pause_ratio=1.0 - voiced_ratio,
        egemaps=None,
    )


def extract_voice_features(audio_base64: str | None) -> VoiceFeatures | None:
    """음성 → 표준 지표. 실패하면 None을 반환하고 상위 단계가 음성 축을 뺀다."""
    if not audio_base64:
        return None

    try:
        signal, sample_rate = decode_wav(audio_base64)
    except Exception:
        logger.exception("오디오 디코드 실패 — WAV(16-bit PCM)인지 확인할 것")
        return None

    if signal.size == 0 or float(np.max(np.abs(signal))) < 1e-6:
        logger.warning("무음 구간 — 마이크가 잡히지 않았을 수 있음")
        return None

    try:
        return _extract_with_opensmile(signal, sample_rate)
    except Exception:
        logger.exception("openSMILE 실패 — parselmouth로 폴백")

    try:
        return _extract_with_parselmouth(signal, sample_rate)
    except Exception:
        logger.exception("parselmouth도 실패 — 음성 축을 제외한다")
        return None
