"""서버측 STT — faster-whisper.

브라우저 Web Speech API 를 대체한다. 두 가지 이유다.

1. **환경에 의존한다.** Chrome 의 Web Speech 는 브라우저 안에서 인식하지 않고
   오디오를 구글 서버로 보낸다. 실측에서 발화 구간 3개가 전부 `network` 오류로
   실패했고(OPEN_QUESTIONS Q7), 심사위원 환경에서도 같은 이유로 실패할 수 있다.
2. **프라이버시 전제와 충돌한다.** 영상 원본을 서버에 안 보내려고 공들여놓고
   음성은 밝히지도 않은 채 구글로 보내고 있었다.

브라우저에서 처리하는 방안은 막혀 있다 — jitter/shimmer/HNR 을 계산하는 브라우저
라이브러리가 없어서 WAV 는 어차피 서버로 올라와야 한다. 그러면 STT 만 브라우저로
옮겨도 얻는 게 없다 (Q7 참조).

★없어도 파이프라인은 돈다. transcript 는 [5] 리포트의 부가 재료이고 판정은
음향 특징에서 나온다. 설치가 안 돼 있거나 모델을 못 받아도 조용히 None 을 돌려준다.
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.services.voice import decode_wav

logger = logging.getLogger(__name__)

_model = None
_load_failed = False

MIN_SEGMENT_CHARS = 1
"""이보다 짧으면 인식 실패로 본다."""


def _get_model():
    """모델은 초기화 비용이 크므로 한 번만 만든다.

    첫 호출에서 HuggingFace 에서 가중치를 내려받는다(base 기준 약 145MB).
    이후에는 로컬 캐시를 쓴다. 실패하면 다시 시도하지 않는다 —
    매 세션마다 수십 초씩 붙잡고 있으면 파이프라인이 멈춘 것처럼 보인다.
    """
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model

    settings = get_settings()
    try:
        from faster_whisper import WhisperModel

        _model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    except Exception as error:  # noqa: BLE001 — 어떤 실패든 파이프라인은 계속돼야 한다
        _load_failed = True
        logger.warning("STT 모델을 준비하지 못했습니다 — 음성 인식 없이 진행합니다: %s", error)
    return _model


def transcribe(audio_base64: str | None) -> str | None:
    """base64 WAV → 인식된 문장. 실패하면 None."""
    if not audio_base64 or not get_settings().stt_enabled:
        return None

    model = _get_model()
    if model is None:
        return None

    try:
        signal, sample_rate = decode_wav(audio_base64)
        segments, _info = model.transcribe(
            signal,
            language="ko",
            # 침묵 구간을 걸러낸다. 발화 10초 중 절반 이상이 침묵인 세션이 있었다
            # (실측 pause_ratio 0.58) — 그대로 넣으면 없는 말을 지어낸다.
            vad_filter=True,
            beam_size=1,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
    except Exception as error:  # noqa: BLE001
        logger.warning("음성 인식에 실패했습니다: %s", error)
        return None

    return text if len(text) >= MIN_SEGMENT_CHARS else None


def fill_missing_transcripts(session) -> int:
    """발화 구간 중 transcript 가 비어 있는 것을 채운다. 채운 개수를 돌려준다.

    ★캡처 업로드가 아니라 분석([5]) 직전에 부른다.
    업로드마다 인식을 돌리면 세션 단계 사이에서 사용자가 기다리게 된다.
    분석 구간에는 이미 "기록을 정리하고 있어요" 화면이 떠 있어 지연이 묻힌다.

    브라우저 STT 가 성공했다면 그 값을 존중하고 건드리지 않는다 —
    서버 인식은 폴백이지 덮어쓰기가 아니다.
    """
    filled = 0
    for capture in session.captures:
        if capture.transcript or not capture.audio_base64:
            continue
        text = transcribe(capture.audio_base64)
        if text:
            capture.transcript = text
            filled += 1
    return filled
