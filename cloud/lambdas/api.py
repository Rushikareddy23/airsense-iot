"""HTTP API (API Gateway HTTP API, payload v2) for the dashboard.

GET /devices                              list devices with their latest reading
GET /devices/{id}/readings?minutes=60     history, downsampled to <= 360 points
PUT /devices/{id}/config                  change thresholds / interval (needs x-admin-token)
"""
import hmac
import json
import os
import time

import boto3
from boto3.dynamodb.conditions import Key

from common import (DEFAULT_CO2_ALERT_PPM, DEFAULT_TEMP_MAX_C, DEVICES_TABLE, READINGS_TABLE, response,
                    to_decimal)

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
MAX_POINTS = 360
METRICS = ["temp_c", "humidity_pct", "pressure_hpa", "co2_ppm", "tvoc_ppb"]


def list_devices(ddb):
    items = ddb.Table(DEVICES_TABLE).scan(Limit=200).get("Items", [])
    now = time.time()
    out = []
    for d in sorted(items, key=lambda d: d["device_id"]):
        last = int(d.get("last_ts", 0))
        out.append({
            "device_id": d["device_id"], "latest": d.get("latest"), "last_ts": last or None,
            "online": bool(last) and now - last < 120,
            "alert_state": d.get("alert_state", "ok"),
            "co2_alert_ppm": d.get("co2_alert_ppm", DEFAULT_CO2_ALERT_PPM),
            "temp_max_c": d.get("temp_max_c", DEFAULT_TEMP_MAX_C),
            "interval_s": d.get("interval_s", 10),
        })
    return response(200, out)


def downsample(items: list[dict], start: int, end: int, max_points: int = MAX_POINTS) -> list[dict]:
    if len(items) <= max_points:
        return [{"ts": int(i["ts"]), **{m: i[m] for m in METRICS}} for i in items]
    width = (end - start) / max_points
    buckets: dict[int, list] = {}
    for i in items:
        buckets.setdefault(min(int((int(i["ts"]) - start) // width), max_points - 1), []).append(i)
    out = []
    for b in (buckets[k] for k in sorted(buckets)):
        point = {"ts": int(b[-1]["ts"])}
        for m in METRICS:
            point[m] = round(sum(float(x[m]) for x in b) / len(b), 2)
        point["co2_ppm_max"] = max(int(x["co2_ppm"]) for x in b)  # don't average away a spike
        out.append(point)
    return out


def readings(ddb, device_id: str, minutes: int):
    end = int(time.time())
    start = end - minutes * 60
    table, items, kwargs = ddb.Table(READINGS_TABLE), [], {}
    while True:  # follow pagination: a 24 h window at 10 s is 8,640 items
        resp = table.query(KeyConditionExpression=Key("device_id").eq(device_id) & Key("ts").between(start, end),
                           **kwargs)
        items += resp["Items"]
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return response(200, {"device_id": device_id, "minutes": minutes, "points": downsample(items, start, end)})


def update_config(ddb, iot, device_id: str, event):
    token = (event.get("headers") or {}).get("x-admin-token", "")
    if not ADMIN_TOKEN or not hmac.compare_digest(token, ADMIN_TOKEN):
        return response(401, {"error": "invalid admin token"})
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return response(400, {"error": "body must be JSON"})
    rules = {"co2_alert_ppm": (int, 600, 5000), "temp_max_c": (float, 15, 60), "interval_s": (int, 5, 3600)}
    changes = {}
    for k, (typ, lo, hi) in rules.items():
        if k in body:
            v = body[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                return response(400, {"error": f"{k} must be a number between {lo} and {hi}"})
            changes[k] = typ(v)
    if not changes:
        return response(400, {"error": f"nothing to update; allowed: {list(rules)}"})
    table = ddb.Table(DEVICES_TABLE)
    if "Item" not in table.get_item(Key={"device_id": device_id}):
        return response(404, {"error": "unknown device"})
    table.update_item(Key={"device_id": device_id},
                      UpdateExpression="SET " + ", ".join(f"{k} = :{k}" for k in changes),
                      ExpressionAttributeValues={f":{k}": to_decimal(v) for k, v in changes.items()})
    desired = {k: v for k, v in changes.items() if k in ("interval_s", "co2_alert_ppm")}
    if desired:  # the device receives these through its Device Shadow delta topic
        iot.update_thing_shadow(thingName=device_id, payload=json.dumps({"state": {"desired": desired}}).encode())
    return response(200, {"device_id": device_id, "updated": changes})


def handler(event, context=None, ddb=None, iot=None):
    ddb = ddb or boto3.resource("dynamodb")
    route = event.get("routeKey", "")
    params = event.get("pathParameters") or {}
    if route == "GET /devices":
        return list_devices(ddb)
    if route == "GET /devices/{id}/readings":
        try:
            minutes = int((event.get("queryStringParameters") or {}).get("minutes", 60))
        except ValueError:
            return response(400, {"error": "minutes must be an integer"})
        return readings(ddb, params["id"], max(5, min(minutes, 60 * 24 * 7)))
    if route == "PUT /devices/{id}/config":
        # Use the account's ATS data endpoint (the default legacy endpoint has an untrusted cert).
        endpoint = os.environ.get("IOT_DATA_ENDPOINT")
        client = iot or boto3.client("iot-data", endpoint_url=f"https://{endpoint}" if endpoint else None)
        return update_config(ddb, client, params["id"], event)
    return response(404, {"error": "not found"})
