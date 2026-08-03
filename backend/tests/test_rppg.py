"""rPPG 모듈 검증 — 합성 신호로 알려진 심박수를 되찾을 수 있는지."""

from __future__ import annotations

import numpy as np
import pytest

from app.schemas.capture import RgbSample
from app.services.rppg import estimate_heart_rate


def _synth(bpm: float, seconds: float = 15.0, fps: float = 30.0, noise: float = 0.0) -> list[RgbSample]:
    """합성 rPPG 신호.

    실제 피부 반사처럼 채널마다 맥동 진폭을 다르게 준다 (green이 가장 강함).
    """
    rng = np.random.default_rng(42)
    t = np.arange(0.0, seconds, 1.0 / fps)
    pulse = np.sin(2 * np.pi * (bpm / 60.0) * t)

    base = np.array([140.0, 110.0, 100.0])
    gain = np.array([0.6, 1.0, 0.4])

    samples = []
    for i, ti in enumerate(t):
        rgb = base + gain * pulse[i]
        if noise > 0:
            rgb = rgb + rng.normal(0.0, noise, 3)
        samples.append(RgbSample(t=float(ti), r=float(rgb[0]), g=float(rgb[1]), b=float(rgb[2])))
    return samples


@pytest.mark.parametrize("bpm", [55.0, 72.0, 95.0, 120.0])
def test_recovers_known_bpm(bpm: float) -> None:
    result = estimate_heart_rate(_synth(bpm), fps=30.0)
    assert result.bpm == pytest.approx(bpm, abs=3.0)
    assert result.confidence > 0.5


def test_noise_lowers_confidence() -> None:
    clean = estimate_heart_rate(_synth(72.0, noise=0.0), fps=30.0)
    noisy = estimate_heart_rate(_synth(72.0, noise=12.0), fps=30.0)
    assert noisy.confidence < clean.confidence


def test_flat_signal_is_rejected() -> None:
    """카메라가 가려졌거나 얼굴을 못 잡은 경우."""
    flat = [RgbSample(t=i / 30.0, r=120.0, g=110.0, b=100.0) for i in range(450)]
    result = estimate_heart_rate(flat, fps=30.0)
    assert result.confidence == 0.0


def test_too_short_is_rejected() -> None:
    result = estimate_heart_rate(_synth(72.0, seconds=1.0), fps=30.0)
    assert result.confidence == 0.0


def test_empty_input_is_rejected() -> None:
    assert estimate_heart_rate(None).confidence == 0.0
    assert estimate_heart_rate([]).confidence == 0.0


def test_hrv_is_not_reported_from_webcam() -> None:
    """30fps 웹캠으로 HRV를 산출한다고 주장하면 안 된다 (OPEN_QUESTIONS Q3)."""
    assert estimate_heart_rate(_synth(72.0), fps=30.0).hrv_rmssd is None


def test_jittered_timestamps_still_work() -> None:
    """브라우저 rAF는 프레임 간격이 흔들린다 — 균일 리샘플링이 이를 흡수해야 한다."""
    rng = np.random.default_rng(7)
    samples = _synth(72.0)
    jittered = [
        RgbSample(t=s.t + float(rng.normal(0, 0.004)), r=s.r, g=s.g, b=s.b)
        for s in samples
    ]
    jittered.sort(key=lambda s: s.t)
    result = estimate_heart_rate(jittered, fps=30.0)
    assert result.bpm == pytest.approx(72.0, abs=4.0)
