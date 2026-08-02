"""서버측 STT.

없어도 파이프라인은 돌아야 한다 — transcript 는 [5] 리포트의 부가 재료이고
판정은 음향 특징에서 나온다. 실제 인식 품질이 아니라 **실패해도 안전한가**와
**브라우저 결과를 존중하는가**를 고정한다.

실제 모델을 돌리는 테스트는 두지 않는다. 모델 다운로드(145MB)와 네트워크가 필요해
CI 에서 불안정하고, 인식 품질은 단위 테스트로 검증할 성질이 아니다.
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.schemas.capture import Capture, Phase, Segment
from app.schemas.session import Session
from app.services import stt


@pytest.fixture(autouse=True)
def _reset_model_cache(monkeypatch):
    """모듈 전역 캐시가 테스트 간에 새지 않게 한다."""
    monkeypatch.setattr(stt, "_model", None)
    monkeypatch.setattr(stt, "_load_failed", False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _speak(transcript: str | None, audio: str | None = "QUJD") -> Capture:
    return Capture(
        session_id="s1",
        segment=Segment.OPTION,
        option_id="opt-a",
        phase=Phase.SPEAK,
        audio_base64=audio,
        transcript=transcript,
    )


def _session(*captures: Capture) -> Session:
    session = Session(decision_id="dec-1")
    session.captures.extend(captures)
    return session


# ── 실패해도 안전한가 ───────────────────────────────────────


def test_no_audio_returns_none() -> None:
    assert stt.transcribe(None) is None
    assert stt.transcribe("") is None


def test_disabled_by_config(monkeypatch) -> None:
    """끄고 싶은 사람이 끌 수 있어야 한다 (설치 용량이 작지 않다)."""
    monkeypatch.setenv("STT_ENABLED", "false")
    get_settings.cache_clear()
    assert stt.transcribe("QUJD") is None


def test_model_load_failure_is_survivable(monkeypatch) -> None:
    """모델을 못 받아도 파이프라인은 계속돼야 한다."""

    def _boom():
        raise RuntimeError("모델 없음")

    monkeypatch.setattr(stt, "_get_model", _boom)
    with pytest.raises(RuntimeError):
        stt._get_model()  # 헬퍼 자체는 던지지만

    # transcribe 는 삼킨다
    monkeypatch.setattr(stt, "_get_model", lambda: None)
    assert stt.transcribe("QUJD") is None


def test_model_load_is_not_retried(monkeypatch) -> None:
    """실패할 때마다 다시 시도하면 매 세션이 수십 초씩 멈춘 것처럼 보인다."""
    attempts = {"n": 0}

    class _Boom:
        def __init__(self, *args, **kwargs):
            attempts["n"] += 1
            raise RuntimeError("no model")

    import sys
    import types

    module = types.ModuleType("faster_whisper")
    module.WhisperModel = _Boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", module)

    assert stt._get_model() is None
    assert stt._get_model() is None
    assert attempts["n"] == 1


def test_transcription_error_is_survivable(monkeypatch) -> None:
    class _Exploding:
        def transcribe(self, *args, **kwargs):
            raise RuntimeError("디코딩 실패")

    monkeypatch.setattr(stt, "_get_model", lambda: _Exploding())
    assert stt.transcribe("QUJD") is None


# ── 브라우저 결과를 존중하는가 ──────────────────────────────


def test_existing_transcript_is_not_overwritten(monkeypatch) -> None:
    """서버 인식은 폴백이지 덮어쓰기가 아니다."""
    monkeypatch.setattr(stt, "transcribe", lambda _audio: "서버가 들은 말")
    session = _session(_speak("브라우저가 들은 말"))

    assert stt.fill_missing_transcripts(session) == 0
    assert session.captures[0].transcript == "브라우저가 들은 말"


def test_missing_transcript_is_filled(monkeypatch) -> None:
    monkeypatch.setattr(stt, "transcribe", lambda _audio: "서버가 들은 말")
    session = _session(_speak(None))

    assert stt.fill_missing_transcripts(session) == 1
    assert session.captures[0].transcript == "서버가 들은 말"


def test_captures_without_audio_are_skipped(monkeypatch) -> None:
    """상상 구간에는 오디오가 없다 — 심박만 잰다."""
    called = {"n": 0}

    def _count(_audio):
        called["n"] += 1
        return "무언가"

    monkeypatch.setattr(stt, "transcribe", _count)
    imagine = Capture(
        session_id="s1", segment=Segment.NEUTRAL, phase=Phase.IMAGINE, audio_base64=None
    )
    session = _session(imagine, _speak(None))

    assert stt.fill_missing_transcripts(session) == 1
    assert called["n"] == 1


def test_empty_recognition_leaves_transcript_none(monkeypatch) -> None:
    """빈 문자열을 채우면 '인식됐다'는 잘못된 신호가 된다."""
    monkeypatch.setattr(stt, "transcribe", lambda _audio: None)
    session = _session(_speak(None))

    assert stt.fill_missing_transcripts(session) == 0
    assert session.captures[0].transcript is None
