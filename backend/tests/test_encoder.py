"""멀티모달 잠재표현.

★상태는 측정값의 나열이 아니다. 손으로 고른 8개 지표를 고정 부호로 더하는 대신
eGeMAPS 88 전부를 하나의 벡터로 보고 거리를 잰다.

여기서 고정하는 것은 **한계**다. 크기는 나오지만 방향은 나오지 않는다.
그 경계가 흐려지면 "우리가 선호를 학습으로 판정한다"는 거짓말이 된다.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.schemas.features import Features, HeartRateFeatures, VoiceFeatures
from app.services import encoder


def _voice(**egemaps: float) -> VoiceFeatures:
    return VoiceFeatures(
        f0_mean=20.0, f0_std=0.2, loudness_mean=0.1, jitter_local=0.02,
        shimmer_local=1.0, hnr=4.0, speech_rate=2.0, pause_ratio=0.5,
        egemaps=egemaps,
    )


def _features(**egemaps: float) -> Features:
    return Features(capture_id="c1", voice=_voice(**egemaps))


KEYS = ["a", "b", "c"]
STATS = (np.array([0.0, 0.0, 0.0]), np.array([1.0, 1.0, 1.0]))


# ── 만들 수 있는가 ──────────────────────────────────────────


def test_latent_needs_egemaps() -> None:
    """8개 지표만으로는 잠재벡터를 만들지 않는다 — 그게 이 작업의 요점이다."""
    bare = Features(
        capture_id="c1",
        voice=VoiceFeatures(
            f0_mean=20.0, f0_std=0.2, loudness_mean=0.1, jitter_local=0.02,
            shimmer_local=1.0, hnr=4.0, speech_rate=2.0, pause_ratio=0.5,
        ),
    )
    assert encoder.latent(bare, KEYS, STATS) is None


def test_latent_uses_all_dimensions() -> None:
    """88개 중 8개만 쓰던 것을 전부 쓴다."""
    z = encoder.latent(_features(a=1.0, b=2.0, c=3.0), KEYS, STATS)
    assert z is not None and len(z) == len(KEYS)


def test_missing_dimension_is_zero_not_dropped() -> None:
    """차원이 빠지면 벡터 길이가 달라져 거리를 못 잰다."""
    z = encoder.latent(_features(a=1.0), KEYS, STATS)
    assert z is not None and len(z) == len(KEYS)


# ── 표준화 ─────────────────────────────────────────────────


def test_standardization_prevents_large_dimensions_dominating() -> None:
    """eGeMAPS 차원들은 크기가 제각각이다 (F0 는 20 남짓, jitter 는 0.02).

    표준화 없이 거리를 재면 큰 차원이 전부를 결정한다.
    """
    stats = (np.array([0.0, 0.0]), np.array([100.0, 0.01]))
    z = encoder.latent(_features(a=100.0, b=0.01), ["a", "b"], stats)
    assert z is not None
    # 두 차원이 각자 1σ 만큼 떨어졌으므로 기여가 같아야 한다.
    assert z[0] == pytest.approx(z[1], rel=1e-6)


def test_corpus_needs_enough_clips() -> None:
    """표본이 몇 개 없으면 표준편차 추정이 무의미하다. 근거 없는 거리보다 없는 게 낫다."""
    assert encoder.MIN_CORPUS_CLIPS >= 4


# ── 거리 ───────────────────────────────────────────────────


def test_identical_vectors_have_zero_distance() -> None:
    v = np.array([1.0, 2.0, 3.0])
    assert encoder.cosine_distance(v, v) == pytest.approx(0.0, abs=1e-9)


def test_opposite_vectors_are_far() -> None:
    v = np.array([1.0, 0.0])
    assert encoder.cosine_distance(v, -v) == pytest.approx(2.0, abs=1e-9)


def test_scaling_does_not_change_distance() -> None:
    """녹음 음량이나 마이크 거리로 전체가 밀려도 방향은 덜 흔들린다.

    실측에서 조건 차이로 지표가 통째로 밀리는 일이 있었다 (EXTREME_DELTA).
    """
    a, b = np.array([1.0, 2.0]), np.array([2.0, 1.0])
    assert encoder.cosine_distance(a, b) == pytest.approx(
        encoder.cosine_distance(a * 5.0, b), abs=1e-9
    )


def test_zero_vector_is_survivable() -> None:
    assert encoder.cosine_distance(np.zeros(3), np.array([1.0, 0.0, 0.0])) == 0.0


# ── 한계를 코드로 고정한다 ──────────────────────────────────


def test_text_is_stored_but_not_fused() -> None:
    """★측정해보고 껐다.

        음성   세션 안 0.964  세션 간 1.115   +0.152  정보 있음
        텍스트 세션 안 0.630  세션 간 0.593   -0.037  역전

    임베딩은 계속 저장한다 — 나중에 head 학습의 입력이 되고, STT 가 좋아지면
    이 판단이 뒤집힐 수 있다. 다시 켜기 전에 위 측정을 다시 해야 한다.
    """
    assert encoder.FUSE_TEXT is False

    features = _features(a=1.0, b=1.0, c=1.0)
    features.text_embedding = [1.0] * 16
    z = encoder.latent(features, KEYS, STATS)
    assert z is not None
    assert len(z) == len(KEYS), "텍스트가 섞이면 길이가 늘어난다"


def test_low_confidence_heart_rate_is_excluded() -> None:
    """신뢰도 미달 심박이 잠재벡터에 들어가면 잡음이 좌표가 된다."""
    features = _features(a=1.0, b=1.0, c=1.0)
    features.hr = HeartRateFeatures(bpm=80.0, confidence=0.1, snr_db=-6.0)
    assert len(encoder.latent(features, KEYS, STATS)) == len(KEYS)

    features.hr = HeartRateFeatures(bpm=80.0, confidence=0.9, snr_db=9.0)
    assert len(encoder.latent(features, KEYS, STATS)) == len(KEYS) + 1
