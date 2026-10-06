import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import make_secrets  # noqa: E402
import simulate  # noqa: E402


def test_secrets_header_escapes_and_embeds_pems():
    h = make_secrets.build_header("dev-1", "abc-ats.iot.us-east-1.amazonaws.com", 'my "wifi"', "p\\w",
                                  "-----BEGIN CERTIFICATE-----\nCA\n-----END CERTIFICATE-----",
                                  "CERT", "KEY")
    assert '#define WIFI_SSID "my \\"wifi\\""' in h and '#define WIFI_PASSWORD "p\\\\w"' in h
    assert 'static const char DEVICE_PRIVATE_KEY[] = R"PEM(\nKEY\n)PEM";' in h


def test_simulated_readings_pass_ingest_validation():
    import ingest
    room = simulate.Room("room-1", seed=1, force_occupants=10)
    now = 1_780_000_000
    readings = [room.step(now + i * 60, 60) for i in range(240)]
    for r in readings:
        ingest.validate({**r, "topic_device": "room-1"}, now + 240 * 60)
    assert readings[-1]["co2_ppm"] > 1500 > readings[0]["co2_ppm"]  # crowded room gets stuffy
