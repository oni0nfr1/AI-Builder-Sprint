from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import HTTPException

from app.routers import diagnostics
from app.schemas.diagnostics import RppgComparisonRequest


def _rgb_series(bpm: float, seconds: float = 15.0, fps: float = 30.0) -> list[dict]:
    t = np.arange(0.0, seconds, 1.0 / fps)
    pulse = np.sin(2 * np.pi * (bpm / 60.0) * t)
    return [
        {
            "t": float(ti),
            "r": 140.0 + 0.6 * pulse[index],
            "g": 110.0 + 1.0 * pulse[index],
            "b": 100.0 + 0.4 * pulse[index],
        }
        for index, ti in enumerate(t)
    ]


def _body() -> dict:
    return {
        "rgb_series": _rgb_series(72.0),
        "fps": 30.0,
        "duration_sec": 15.0,
        "reference_bpm": 72.0,
        "rppg_web": {
            "source": "rppg-web",
            "version": "0.14.0",
            "bpm": 74.0,
            "confidence": 0.72,
            "signal_quality": 0.8,
            "agreement": 0.9,
            "reason_codes": [],
            "stable_sample_count": 8,
        },
    }


def test_compare_returns_both_results_without_storage(monkeypatch) -> None:
    monkeypatch.setattr(
        diagnostics,
        "get_settings",
        lambda: SimpleNamespace(rppg_diagnostics_enabled=True),
    )

    response = diagnostics.compare_rppg(RppgComparisonRequest.model_validate(_body()))

    data = response.data
    assert data is not None
    assert data.server_chrom.source == "server_rgb"
    assert abs(data.server_chrom.bpm - 72.0) <= 1.0
    assert data.rppg_web is not None
    assert data.rppg_web.bpm == 74.0
    assert data.web_absolute_error == 2.0
    assert data.server_absolute_error is not None
    assert data.server_absolute_error <= 1.0


def test_compare_is_closed_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        diagnostics,
        "get_settings",
        lambda: SimpleNamespace(rppg_diagnostics_enabled=False),
    )

    with pytest.raises(HTTPException) as raised:
        diagnostics.compare_rppg(RppgComparisonRequest.model_validate(_body()))
    assert raised.value.status_code == 404


def test_web_only_comparison_does_not_create_server_result(monkeypatch) -> None:
    monkeypatch.setattr(
        diagnostics,
        "get_settings",
        lambda: SimpleNamespace(rppg_diagnostics_enabled=True),
    )
    body = _body()
    body["rgb_series"] = None
    body["fps"] = 0.0

    response = diagnostics.compare_rppg(RppgComparisonRequest.model_validate(body))

    assert response.data is not None
    assert response.data.server_chrom is None
    assert response.data.rppg_web is not None
    assert response.data.web_absolute_error == 2.0
    assert response.data.server_absolute_error is None
    assert response.data.bpm_difference is None


def test_comparison_rejects_request_without_either_measurement() -> None:
    body = _body()
    body["rgb_series"] = None
    body["rppg_web"] = None
    body["fps"] = 0.0

    with pytest.raises(ValueError):
        RppgComparisonRequest.model_validate(body)
