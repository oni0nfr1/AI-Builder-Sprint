"""[2] 심박 추출 — 웹캠 rPPG (remote photoplethysmography).

브라우저가 보낸 얼굴 ROI의 RGB 평균 시계열에서 심박수를 추정한다.

    resample → CHROM 결합 → detrend → bandpass(0.7~4Hz) → FFT → 피크 = BPM

정확도 한계를 전제로 설계했다. 웹캠 rPPG는 조명·움직임에 민감해서 절대치를
믿을 수 없다. 그래서 (1) `confidence`를 항상 함께 반환하고, (2) 상위 단계는
절대치가 아닌 **상대 변화율**만 쓴다. 개선안은 OPEN_QUESTIONS Q3.

말하는 동안이 아니라 상상 구간(정지)에서 재는 이유도 같다 — 발화 중에는
얼굴 근육이 움직여 신호가 깨진다.
"""

from __future__ import annotations

import numpy as np
from scipy import signal as sp_signal

from app.schemas.capture import RgbSample
from app.schemas.features import HeartRateFeatures

BAND_LOW_HZ = 0.7
"""42 bpm."""

BAND_HIGH_HZ = 4.0
"""240 bpm."""

MIN_SAMPLES = 64
MIN_DURATION_SEC = 4.0
TARGET_FPS = 30.0

_SNR_DB_FOR_FULL_CONFIDENCE = 10.0
"""이 SNR 이상이면 confidence 1.0. 실측 데이터를 보고 조정할 값 (Q3)."""


def _uniform_resample(
    samples: list[RgbSample], fps: float
) -> tuple[np.ndarray, np.ndarray, float]:
    """브라우저 requestAnimationFrame은 프레임 간격이 흔들린다. 균일 격자로 다시 샘플링한다."""
    t = np.array([s.t for s in samples], dtype=float)
    rgb = np.array([[s.r, s.g, s.b] for s in samples], dtype=float)

    duration = float(t[-1] - t[0])
    effective_fps = fps if fps > 1.0 else (len(samples) - 1) / max(duration, 1e-6)
    effective_fps = float(np.clip(effective_fps, 10.0, 120.0))

    n = max(int(duration * effective_fps), MIN_SAMPLES)
    grid = np.linspace(t[0], t[-1], n)
    resampled = np.column_stack(
        [np.interp(grid, t, rgb[:, ch]) for ch in range(3)]
    )
    return grid, resampled, effective_fps


def _chrom(rgb: np.ndarray) -> np.ndarray:
    """CHROM (de Haan & Jeanne, 2013) — 색차 기반 결합.

    green 채널 단독보다 조명 변화와 미세한 움직임에 강하다.
    """
    means = rgb.mean(axis=0)
    means[means == 0] = 1e-6
    rn, gn, bn = (rgb / means).T

    x = 3.0 * rn - 2.0 * gn
    y = 1.5 * rn + gn - 1.5 * bn

    std_y = float(np.std(y))
    alpha = float(np.std(x)) / std_y if std_y > 1e-9 else 0.0
    return x - alpha * y


def _bandpass(x: np.ndarray, fs: float) -> np.ndarray:
    nyq = fs / 2.0
    high = min(BAND_HIGH_HZ / nyq, 0.99)
    low = BAND_LOW_HZ / nyq
    if not (0 < low < high < 1):
        return x
    b, a = sp_signal.butter(4, [low, high], btype="band")
    return sp_signal.filtfilt(b, a, x)


def _peak_and_snr(x: np.ndarray, fs: float) -> tuple[float, float]:
    """대역 내 최대 피크 주파수와 SNR(dB)을 반환한다.

    SNR = (피크 + 2배 고조파 주변 대역 전력) / (나머지 대역 전력)
    심박 신호는 고조파를 동반하므로, 고조파가 함께 보이면 진짜 신호일 가능성이 높다.
    """
    n = len(x)
    window = np.hanning(n)
    spectrum = np.abs(np.fft.rfft(x * window)) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)

    band = (freqs >= BAND_LOW_HZ) & (freqs <= BAND_HIGH_HZ)
    if not band.any() or spectrum[band].sum() <= 1e-12:
        return 0.0, -np.inf

    band_freqs = freqs[band]
    band_power = spectrum[band]
    peak_hz = float(band_freqs[int(np.argmax(band_power))])

    tolerance = 0.12  # Hz
    signal_mask = np.abs(band_freqs - peak_hz) <= tolerance
    signal_mask |= np.abs(band_freqs - 2.0 * peak_hz) <= tolerance

    signal_power = float(band_power[signal_mask].sum())
    noise_power = float(band_power[~signal_mask].sum())
    if noise_power <= 0:
        return peak_hz, _SNR_DB_FOR_FULL_CONFIDENCE

    return peak_hz, 10.0 * float(np.log10(signal_power / noise_power))


def _confidence_from_snr(snr_db: float) -> float:
    if not np.isfinite(snr_db):
        return 0.0
    return float(np.clip((snr_db + _SNR_DB_FOR_FULL_CONFIDENCE) / (2 * _SNR_DB_FOR_FULL_CONFIDENCE), 0.0, 1.0))


def estimate_heart_rate(
    samples: list[RgbSample] | None, fps: float = 0.0
) -> HeartRateFeatures:
    """RGB 시계열 → 심박수.

    신호가 부족하거나 품질이 낮으면 `confidence`를 낮게 반환한다.
    호출부는 절대 `bpm`만 보고 판단하면 안 된다 — CONFIDENCE_FLOOR 미만이면
    [4] 판정에서 심박 축이 통째로 제외된다.
    """
    if not samples or len(samples) < MIN_SAMPLES:
        return HeartRateFeatures(bpm=0.0, confidence=0.0, snr_db=-99.0)

    duration = float(samples[-1].t - samples[0].t)
    if duration < MIN_DURATION_SEC:
        return HeartRateFeatures(bpm=0.0, confidence=0.0, snr_db=-99.0)

    _, rgb, fs = _uniform_resample(samples, fps)

    # 채널별 *시간축* 변동을 본다. rgb 전체의 std를 쓰면 채널 간 밝기 차이
    # (예: r=120, g=110, b=100)를 변동으로 오인해 평평한 신호를 통과시킨다.
    if float(rgb.std(axis=0).max()) < 1e-6:
        # 카메라가 가려졌거나 얼굴을 못 잡은 경우
        return HeartRateFeatures(bpm=0.0, confidence=0.0, snr_db=-99.0)

    combined = _chrom(rgb)
    detrended = sp_signal.detrend(combined)

    # 정규화해서 이후 절대 임계값이 신호 크기와 무관하게 동작하게 한다.
    scale = float(np.std(detrended))
    if scale < 1e-9:
        return HeartRateFeatures(bpm=0.0, confidence=0.0, snr_db=-99.0)

    filtered = _bandpass(detrended / scale, fs)

    peak_hz, snr_db = _peak_and_snr(filtered, fs)
    bpm = peak_hz * 60.0

    confidence = _confidence_from_snr(snr_db)
    if not (40.0 <= bpm <= 200.0):
        confidence = 0.0

    return HeartRateFeatures(
        bpm=round(bpm, 1),
        confidence=round(confidence, 3),
        snr_db=round(snr_db, 2) if np.isfinite(snr_db) else -99.0,
        hrv_rmssd=None,  # 30fps 웹캠으로는 신뢰할 수 없다. 웨어러블 연동 시 채움
    )
