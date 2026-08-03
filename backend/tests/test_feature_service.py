from app.schemas.capture import Capture, Phase, Segment
from app.services.feature_service import extract


def test_uses_client_rppg_measurement_without_rgb_series() -> None:
    capture = Capture(
        session_id="session-1",
        segment=Segment.OPTION,
        option_id="option-1",
        phase=Phase.IMAGINE,
        rppg_measurement={
            "source": "rppg-web",
            "version": "0.14.0",
            "bpm": 72.5,
            "confidence": 0.76,
            "signal_quality": 0.81,
            "agreement": 0.9,
            "reason_codes": [],
            "stable_sample_count": 8,
        },
    )

    features = extract(capture)

    assert features.hr is not None
    assert features.hr.bpm == 72.5
    assert features.hr.confidence == 0.76
    assert features.hr.source == "rppg-web"
    assert features.hr.snr_db is None
    assert features.hr.signal_quality == 0.81
    assert features.hr.agreement == 0.9


def test_missing_rppg_measurement_does_not_create_fake_heart_rate() -> None:
    capture = Capture(
        session_id="session-1",
        segment=Segment.OPTION,
        option_id="option-1",
        phase=Phase.IMAGINE,
    )

    features = extract(capture)

    assert features.hr is None
    assert features.as_metrics() == {}
