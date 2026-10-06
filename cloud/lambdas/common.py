import json
import os
from decimal import Decimal

READINGS_TABLE = os.environ.get("READINGS_TABLE", "airsense-readings")
DEVICES_TABLE = os.environ.get("DEVICES_TABLE", "airsense-devices")
ALERT_TOPIC_ARN = os.environ.get("ALERT_TOPIC_ARN", "")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "30"))

DEFAULT_CO2_ALERT_PPM = 1200
DEFAULT_TEMP_MAX_C = 30.0
CO2_HYSTERESIS_PPM = 100      # must drop this far below the threshold to clear an alert
TEMP_HYSTERESIS_C = 1.0

# field -> (type, min, max). Out-of-range values are rejected, not stored.
FIELDS = {
    "ts": (int, 1_600_000_000, 4_000_000_000),
    "temp_c": (float, -40, 85),
    "humidity_pct": (float, 0, 100),
    "pressure_hpa": (float, 300, 1100),
    "co2_ppm": (int, 400, 60000),
    "tvoc_ppb": (int, 0, 60000),
}


def to_decimal(v):
    return Decimal(str(v))


def plain(o):
    """DynamoDB Decimals -> JSON-friendly numbers."""
    if isinstance(o, list):
        return [plain(x) for x in o]
    if isinstance(o, dict):
        return {k: plain(v) for k, v in o.items()}
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    return o


def response(status: int, body) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(plain(body))}
