"""[2] 음성 특징 추출 검증 — 합성 음성 신호로 경로가 살아있는지 확인."""

from __future__ import annotations

import base64
import io

import numpy as np
import pytest
import soundfile as sf

from app.services.voice import decode_wav, extract_voice_features


def _wav_base64(signal: np.ndarray, sample_rate: int = 16000) -> str:
    buffer = io.BytesIO()
    sf.write(buffer, signal, sample_rate, format="WAV", subtype="PCM_16")
    return base64.b64encode(buffer.getvalue()).decode()


def _synth_voice(f0: float = 150.0, seconds: float = 3.0, sample_rate: int = 16000) -> np.ndarray:
    """성대 진동을 흉내낸 합성 음성 — 기본 주파수 + 고조파 + 약간의 흔들림."""
    rng = np.random.default_rng(0)
    t = np.arange(0.0, seconds, 1.0 / sample_rate)
    jitter = 1.0 + 0.004 * np.sin(2 * np.pi * 5.0 * t)
    signal = sum(
        (1.0 / h) * np.sin(2 * np.pi * f0 * h * t * jitter) for h in range(1, 6)
    )
    envelope = 0.5 * (1 + np.sin(2 * np.pi * 0.7 * t))  # 발화/휴지 리듬
    return (0.3 * signal * envelope + 0.001 * rng.normal(size=t.size)).astype(np.float32)


def test_decode_wav_roundtrip() -> None:
    signal = _synth_voice()
    decoded, sample_rate = decode_wav(_wav_base64(signal))
    assert sample_rate == 16000
    assert decoded.shape[0] == pytest.approx(signal.shape[0], rel=0.01)


def test_extracts_all_contract_metrics() -> None:
    features = extract_voice_features(_wav_base64(_synth_voice()))
    assert features is not None
    metrics = features.as_metrics()
    # 계약이 요구하는 8개 음성 지표가 모두 채워져야 한다
    assert len(metrics) == 8
    assert all(np.isfinite(v) for v in metrics.values())


def test_egemaps_88_present() -> None:
    """openSMILE 경로가 살아있으면 eGeMAPS 88개가 그대로 담긴다."""
    features = extract_voice_features(_wav_base64(_synth_voice()))
    assert features is not None
    assert features.egemaps is not None
    assert len(features.egemaps) == 88


def test_higher_pitch_yields_higher_f0() -> None:
    low = extract_voice_features(_wav_base64(_synth_voice(f0=120.0)))
    high = extract_voice_features(_wav_base64(_synth_voice(f0=220.0)))
    assert low is not None and high is not None
    assert high.f0_mean > low.f0_mean


def test_silence_is_rejected() -> None:
    """마이크가 안 잡힌 경우 — 음성 축을 빼야지 0으로 채우면 안 된다."""
    silence = np.zeros(16000, dtype=np.float32)
    assert extract_voice_features(_wav_base64(silence)) is None


def test_missing_audio_is_rejected() -> None:
    assert extract_voice_features(None) is None
    assert extract_voice_features("") is None


def test_corrupt_audio_is_rejected() -> None:
    """WebM/Opus를 그대로 보내면 여기서 걸린다 (계약: 16-bit PCM WAV)."""
    assert extract_voice_features(base64.b64encode(b"not a wav file").decode()) is None
