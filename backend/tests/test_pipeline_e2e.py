"""파이프라인 전체 통과 검증 — [0] 고민 등록부터 [8] 회고까지.

LLM 키 없이 규칙 기반 폴백만으로도 끝까지 돌아야 한다.
"""

from __future__ import annotations

import base64
import io
import os
import tempfile

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    db_path = os.path.join(tempfile.mkdtemp(), "test.db")
    os.environ["DB_PATH"] = db_path
    os.environ["UPSTAGE_API_KEY"] = ""

    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def _wav_b64(f0: float, seconds: float = 3.0, sample_rate: int = 16000) -> str:
    t = np.arange(0.0, seconds, 1.0 / sample_rate)
    signal = sum((1.0 / h) * np.sin(2 * np.pi * f0 * h * t) for h in range(1, 6))
    envelope = 0.5 * (1 + np.sin(2 * np.pi * 0.7 * t))
    buffer = io.BytesIO()
    sf.write(buffer, (0.3 * signal * envelope).astype(np.float32), sample_rate,
             format="WAV", subtype="PCM_16")
    return base64.b64encode(buffer.getvalue()).decode()


def _rgb_series(bpm: float, seconds: float = 15.0, fps: float = 30.0) -> list[dict]:
    t = np.arange(0.0, seconds, 1.0 / fps)
    pulse = np.sin(2 * np.pi * (bpm / 60.0) * t)
    return [
        {"t": float(ti), "r": 140.0 + 0.6 * pulse[i],
         "g": 110.0 + 1.0 * pulse[i], "b": 100.0 + 0.4 * pulse[i]}
        for i, ti in enumerate(t)
    ]


def _post_capture(client, session_id, *, segment, option_id, phase, f0=None, bpm=None):
    body = {
        "session_id": session_id,
        "segment": segment,
        "option_id": option_id,
        "phase": phase,
        "rgb_series": _rgb_series(bpm) if bpm is not None else None,
        "audio_base64": _wav_b64(f0) if f0 is not None else None,
        "transcript": None,
        "fps": 30.0 if bpm is not None else 0.0,
        "duration_sec": 15.0 if bpm is not None else 3.0,
    }
    response = client.post(f"/sessions/{session_id}/captures", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_full_pipeline(client) -> None:
    assert client.get("/health").json()["data"]["status"] == "up"

    # [0] 고민 등록
    created = client.post("/decisions", json={"raw_input": "이직한다 vs 남는다"}).json()
    assert created["ok"] is True
    decision = created["data"]
    assert len(decision["options"]) == 2
    option_a, option_b = decision["options"]

    # 두 선택지의 프롬프트는 구조적으로 대칭이어야 한다
    assert option_a["imagine_prompt"] != option_b["imagine_prompt"]
    assert len(option_a["imagine_prompt"]) == pytest.approx(
        len(option_b["imagine_prompt"]), abs=len(option_a["label"]) + len(option_b["label"])
    )

    # 세션 시작
    session = client.post("/sessions", json={"decision_id": decision["id"]}).json()["data"]
    session_id = session["id"]

    # [1][2] 중립 앵커 — default 심박 + default 음성
    _post_capture(client, session_id, segment="neutral", option_id=None,
                  phase="imagine", bpm=72.0)
    _post_capture(client, session_id, segment="neutral", option_id=None,
                  phase="speak", f0=150.0)

    # [1][2] 선택지 A — 피치 높고 심박 낮음
    hr_a = _post_capture(client, session_id, segment="option", option_id=option_a["id"],
                         phase="imagine", bpm=70.0)
    assert hr_a["data"]["hr"]["confidence"] > 0.5
    voice_a = _post_capture(client, session_id, segment="option", option_id=option_a["id"],
                            phase="speak", f0=200.0)
    assert voice_a["data"]["voice"]["egemaps"] is not None

    # [1][2] 선택지 B — 피치 낮고 심박 높음
    _post_capture(client, session_id, segment="option", option_id=option_b["id"],
                  phase="imagine", bpm=88.0)
    _post_capture(client, session_id, segment="option", option_id=option_b["id"],
                  phase="speak", f0=140.0)

    # [3][4][5] 분석 → 리포트
    analyzed = client.post(f"/sessions/{session_id}/analyze")
    assert analyzed.status_code == 200, analyzed.text
    report = analyzed.json()["data"]

    # 리포트 순서가 곧 설계다: 상태 → 관찰 → 태깅 → 자기 진술
    assert report["state_note"]
    assert len(report["observations"]) >= 1
    assert report["tagging_question"]
    assert report["body_tag_options"]
    assert report["self_statement_question"]

    # ★ 내부 판정은 사용자에게 노출되지 않는다
    assert "lean" not in analyzed.text
    assert "confidence" not in analyzed.text

    # 판정 자체는 세션에 저장되어 있다
    stored = client.get(f"/sessions/{session_id}").json()["data"]
    assert stored["verdict"]["preference"]["lean"] in {"A", "B", "none", "contradictory"}
    assert stored["delta"]["state"]["default_available"] is True

    # [6] 사용자 태깅 — self_lean이 핵심 산출물
    annotation = client.post(
        f"/sessions/{session_id}/annotation",
        json={
            "session_id": session_id,
            "option_id": option_a["id"],
            "body_tags": ["가슴 답답함"],
            "body_tag_custom": None,
            "self_lean_option_id": option_a["id"],
            "self_lean_note": "말하다 보니 A쪽인 것 같다",
        },
    )
    assert annotation.status_code == 200, annotation.text

    # [8] 회고 루프 — 1주부터 시작
    retro = client.post(
        f"/sessions/{session_id}/retrospective",
        json={"session_id": session_id, "horizon": "1w",
              "chosen_option_id": option_a["id"], "satisfaction": 4, "note": None},
    )
    assert retro.status_code == 200, retro.text

    # [8] 가치관 지도 — 사용자가 자기 입으로 말한 것으로 집계된다
    value_map = client.get("/value-map").json()["data"]
    assert len(value_map["axes"]) >= 1
    assert option_a["label"] in value_map["axes"][0]["lean_pattern"]


def test_error_envelope(client) -> None:
    """raw traceback을 노출하지 않고 팀 컨벤션 형식으로 변환한다."""
    response = client.get("/sessions/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["ok"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "http_error"


def test_validation_error_envelope(client) -> None:
    response = client.post("/decisions", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
