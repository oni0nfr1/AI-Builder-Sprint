"""멀티모달 잠재표현.

★상태는 측정값의 나열이 아니다.

`[4]` 판정은 지금까지 이렇게 했다.

    score = Σ(부호[k] × Δ[k]) / Σ|부호[k]|      부호는 손으로 정한 8개

손으로 정한 선형 사영이다. 상호작용이 없고(“jitter 가 오르면서 **동시에** hnr 이
떨어지는” 패턴을 못 본다), 맥락이 없고(이직과 점심에 같은 부호표), 음성과 심박을
각각 계산해 평균한다 — 혼합이 아니라 병렬이다.

여기서는 갈래들을 하나의 벡터로 섞는다.

    z_voice  eGeMAPS 88차원 전부   ← 지금까지 8개만 쓰고 80개를 버리고 있었다
    hr       심박                  ← 신뢰도 미달이면 빠진다
    z_text   발화 의미 벡터        ← 저장은 하되 **지금은 섞지 않는다** (FUSE_TEXT 참조)

**표준화 기준은 default(중립 앵커)다.** 절대 위치가 아니라 "평소로부터 얼마나
떨어졌는가"를 벡터로 표현한다 — 두 축의 분리(§3)를 잠재공간에서 그대로 지킨다.

한계를 분명히 해둔다. 라벨이 없으므로 **방향(어느 쪽 선호인가)은 여기서 나오지
않는다.** 크기와 상태만 나온다. 방향은 `annotation.self_lean_option_id` 가 쌓여야
학습할 수 있고, 그때 이 벡터가 그대로 입력이 된다 (CLAUDE.md §4 교체 지점).
"""

from __future__ import annotations

import logging

import numpy as np

from app.core import storage
from app.schemas.features import CONFIDENCE_FLOOR, Features
from app.services.llm import embed_text

logger = logging.getLogger(__name__)

MIN_CORPUS_CLIPS = 4
"""표준편차를 추정하려면 최소 이 정도는 있어야 한다. 미만이면 잠재 축을 쓰지 않는다."""

FUSE_TEXT = False
"""★텍스트 임베딩을 거리 계산에 섞을 것인가. 지금은 **아니다.**

측정해보고 껐다. 판정 기준은 "같은 세션 안의 거리가 세션 간 거리보다 작은가" —
그래야 그 표현이 세션 고유의 무언가를 담고 있다는 뜻이다.

    음성 (eGeMAPS 88 표준화)   세션 안 0.964  세션 간 1.115   +0.152  정보 있음
    텍스트 (Solar 4096)        세션 안 0.630  세션 간 0.593   -0.037  역전

텍스트는 같은 세션 안에서 오히려 더 멀다. 지금 STT 품질로는 발화가 뭉개져
("아침에 일어나서 사인길라크 등록 하기를...") A/B 차이를 담지 못하고, 세션 간에는
다들 비슷하게 뭉개져 가까워진다. 게다가 4096차원이 88차원을 압도해 섞으면 정보
있는 쪽을 덮는다.

**임베딩은 계속 저장한다** — 나중에 head 를 학습할 때 입력이 되고, STT 가 좋아지면
이 판단이 뒤집힐 수 있다. 다시 켜기 전에 위 측정을 다시 할 것 (OPEN_QUESTIONS Q8).
"""

TEXT_WEIGHT = 0.5
"""FUSE_TEXT 를 켤 때의 가중치. 차원 수가 그대로 영향력이 되지 않도록 누른다."""

_EPSILON = 1e-9


def egemaps_keys() -> list[str]:
    """eGeMAPS 차원 순서를 고정한다. 순서가 흔들리면 벡터가 의미를 잃는다."""
    for raw in storage.list_all("sessions"):
        for feature in raw.get("features") or []:
            voice = feature.get("voice") or {}
            keys = voice.get("egemaps")
            if keys:
                return sorted(keys)
    return []


def corpus_stats(keys: list[str]) -> tuple[np.ndarray, np.ndarray] | None:
    """지금까지 쌓인 모든 발화의 평균·표준편차.

    eGeMAPS 차원들은 크기가 제각각이다(F0 는 20 남짓, jitter 는 0.02). 표준화 없이
    거리를 재면 큰 차원이 전부를 결정한다.
    """
    rows: list[list[float]] = []
    for raw in storage.list_all("sessions"):
        for feature in raw.get("features") or []:
            egemaps = (feature.get("voice") or {}).get("egemaps")
            if not egemaps:
                continue
            rows.append([float(egemaps.get(k, 0.0)) for k in keys])

    if len(rows) < MIN_CORPUS_CLIPS:
        return None
    matrix = np.array(rows, dtype=float)
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0)
    std[std < _EPSILON] = 1.0  # 한 번도 변한 적 없는 차원은 거리에 기여하지 않는다
    return mean, std


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > _EPSILON else vector


def latent(
    features: Features,
    keys: list[str],
    stats: tuple[np.ndarray, np.ndarray],
) -> np.ndarray | None:
    """한 구간의 잠재벡터. 음성이 없으면 만들 수 없다."""
    if features.voice is None or not features.voice.egemaps:
        return None

    mean, std = stats
    voice = np.array([float(features.voice.egemaps.get(k, 0.0)) for k in keys])
    parts = [_unit((voice - mean) / std)]

    if FUSE_TEXT and features.text_embedding:
        parts.append(TEXT_WEIGHT * _unit(np.array(features.text_embedding, dtype=float)))

    if features.hr is not None and features.hr.confidence >= CONFIDENCE_FLOOR:
        # 심박은 한 축이라 정규화할 게 없다. 대략적인 생리 범위로 눌러 넣는다.
        parts.append(np.array([(features.hr.bpm - 70.0) / 30.0]))

    return np.concatenate(parts)


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """0(같음) ~ 2(정반대). 크기가 아니라 **방향**의 차이를 본다.

    발화 길이나 녹음 음량이 달라도 방향은 덜 흔들린다 — 실측에서 조건 차이로
    지표가 통째로 밀리는 일이 있었다(EXTREME_DELTA).
    """
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < _EPSILON or nb < _EPSILON:
        return 0.0
    return float(1.0 - np.dot(a, b) / (na * nb))


async def attach_text_embedding(features: Features, transcript: str | None) -> None:
    """발화 내용을 의미 벡터로 바꿔 붙인다. 실패해도 파이프라인은 돈다."""
    if not transcript or features.text_embedding:
        return
    vector = await embed_text(transcript)
    if vector:
        features.text_embedding = vector
