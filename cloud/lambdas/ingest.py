"""Triggered by the AWS IoT rule for every telemetry message.

1. validate the payload (types, physical ranges, timestamp sanity, device identity)
2. store the reading (idempotent: QoS-1 redeliveries overwrite the same key)
3. update the device's latest reading only if this one is newer (buffered readings can
   arrive out of order after a reconnect)
4. raise / clear threshold alerts with hysteresis and a conditional state transition, so
   concurrent invocations never send duplicate alerts
"""
import logging
import time

import boto3
from botocore.exceptions import ClientError

from common import (ALERT_TOPIC_ARN, CO2_HYSTERESIS_PPM, DEFAULT_CO2_ALERT_PPM, DEFAULT_TEMP_MAX_C,
                    DEVICES_TABLE, FIELDS, READINGS_TABLE, RETENTION_DAYS, TEMP_HYSTERESIS_C, to_decimal)

log = logging.getLogger()
log.setLevel(logging.INFO)
FRESH_SECONDS = 600            # only alert on readings from the last 10 minutes
MAX_FUTURE_SKEW_S = 300


class InvalidReading(ValueError):
    pass


def validate(evt: dict, now: float) -> dict:
    device = evt.get("device_id")
    if not isinstance(device, str) or not device or len(device) > 64:
        raise InvalidReading("missing device_id")
    if evt.get("topic_device") and evt["topic_device"] != device:
        raise InvalidReading("device_id does not match MQTT topic")
    out = {"device_id": device}
    for name, (typ, lo, hi) in FIELDS.items():
        v = evt.get(name)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise InvalidReading(f"{name} missing or not a number")
        if not lo <= v <= hi:
            raise InvalidReading(f"{name}={v} outside [{lo}, {hi}]")
        out[name] = int(v) if typ is int else round(float(v), 2)
    if out["ts"] > now + MAX_FUTURE_SKEW_S:
        raise InvalidReading("timestamp is in the future")
    if out["ts"] < now - RETENTION_DAYS * 86400:
        raise InvalidReading("timestamp older than retention window")
    return out


def breach_state(r: dict, device: dict, currently_alerting: bool) -> tuple[bool, list[str]]:
    co2_limit = int(device.get("co2_alert_ppm", DEFAULT_CO2_ALERT_PPM))
    temp_limit = float(device.get("temp_max_c", DEFAULT_TEMP_MAX_C))
    if currently_alerting:  # hysteresis: need to be clearly back to normal to clear
        co2_limit -= CO2_HYSTERESIS_PPM
        temp_limit -= TEMP_HYSTERESIS_C
    reasons = []
    if r["co2_ppm"] >= co2_limit:
        reasons.append(f"CO2 {r['co2_ppm']} ppm (limit {int(device.get('co2_alert_ppm', DEFAULT_CO2_ALERT_PPM))})")
    if r["temp_c"] >= temp_limit:
        reasons.append(f"temperature {r['temp_c']:.1f} °C (limit {float(device.get('temp_max_c', DEFAULT_TEMP_MAX_C)):.1f})")
    return bool(reasons), reasons


def handler(event, context=None, ddb=None, sns=None, now: float | None = None):
    now = now or time.time()
    ddb = ddb or boto3.resource("dynamodb")
    sns = sns or boto3.client("sns")
    try:
        r = validate(event, now)
    except InvalidReading as e:
        log.warning("rejected reading: %s | %s", e, {k: event.get(k) for k in ("device_id", "ts")})
        return {"status": "rejected", "reason": str(e)}

    readings, devices = ddb.Table(READINGS_TABLE), ddb.Table(DEVICES_TABLE)
    item = {k: to_decimal(v) if isinstance(v, float) else v for k, v in r.items()}
    item["expires_at"] = r["ts"] + RETENTION_DAYS * 86400  # DynamoDB TTL
    readings.put_item(Item=item)

    latest = {k: v for k, v in item.items() if k not in ("device_id", "expires_at")}
    try:
        devices.update_item(
            Key={"device_id": r["device_id"]},
            UpdateExpression="SET latest = :r, last_ts = :ts",
            # "<=" so a retried invocation for the same reading still reaches the alert step.
            ConditionExpression="attribute_not_exists(last_ts) OR last_ts <= :ts",
            ExpressionAttributeValues={":r": latest, ":ts": r["ts"]})
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return {"status": "stored", "latest": False}  # older buffered reading: history only

    if now - r["ts"] > FRESH_SECONDS:
        return {"status": "stored", "latest": True, "alert": None}
    device = devices.get_item(Key={"device_id": r["device_id"]}, ConsistentRead=True)["Item"]
    alerting = device.get("alert_state") == "alerting"
    breached, reasons = breach_state(r, device, alerting)
    if breached == alerting:
        return {"status": "stored", "latest": True, "alert": None}

    new, old = ("alerting", device.get("alert_state", "ok")) if breached else ("ok", "alerting")
    try:  # only one invocation can win this transition
        devices.update_item(
            Key={"device_id": r["device_id"]},
            UpdateExpression="SET alert_state = :new, alert_changed_ts = :ts",
            ConditionExpression="attribute_not_exists(alert_state) OR alert_state = :old",
            ExpressionAttributeValues={":new": new, ":old": old, ":ts": r["ts"]})
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return {"status": "stored", "latest": True, "alert": None}
        raise
    subject = (f"[ALERT] {r['device_id']}: " + ", ".join(reasons)) if breached else f"[RESOLVED] {r['device_id']} back to normal"
    body = (f"{subject}\nTemperature {r['temp_c']} °C, humidity {r['humidity_pct']} %, "
            f"CO2 {r['co2_ppm']} ppm, TVOC {r['tvoc_ppb']} ppb at {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(r['ts']))}")
    try:
        sns.publish(TopicArn=ALERT_TOPIC_ARN, Subject=subject[:100], Message=body)
    except Exception:
        # Roll the state back so the Lambda retry (IoT invokes asynchronously, with retries)
        # re-attempts the alert instead of silently losing it.
        devices.update_item(Key={"device_id": r["device_id"]}, UpdateExpression="SET alert_state = :old",
                            ExpressionAttributeValues={":old": old})
        raise
    return {"status": "stored", "latest": True, "alert": new}
