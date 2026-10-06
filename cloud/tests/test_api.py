import json
import time

import pytest
from conftest import reading

import api
import ingest


class FakeIot:
    def __init__(self):
        self.updates = []

    def update_thing_shadow(self, thingName, payload):
        self.updates.append((thingName, json.loads(payload)))


def call(aws, route, iot=None, **kw):
    ddb, _ = aws
    out = api.handler({"routeKey": route, **kw}, ddb=ddb, iot=iot or FakeIot())
    return out["statusCode"], json.loads(out["body"])


def seed(aws, n, step=10):
    ddb, _ = aws
    now = int(time.time())
    for i in range(n):
        ingest.handler(reading(ts=now - (n - i) * step, co2_ppm=600 + (i % 50)), ddb=ddb,
                       sns=type("S", (), {"publish": lambda *a, **k: None})(), now=now)
    return now


def test_list_devices(aws):
    seed(aws, 3)
    code, body = call(aws, "GET /devices")
    assert code == 200 and body[0]["device_id"] == "dev-1" and body[0]["online"] is True
    assert body[0]["latest"]["co2_ppm"] == 602


def test_readings_paginates_and_downsamples(aws):
    seed(aws, 2000, step=20)  # ~11 hours of data
    code, body = call(aws, "GET /devices/{id}/readings", pathParameters={"id": "dev-1"},
                      queryStringParameters={"minutes": "720"})
    pts = body["points"]
    assert code == 200 and 300 <= len(pts) <= 360
    assert pts == sorted(pts, key=lambda p: p["ts"])
    assert all(p["co2_ppm_max"] >= p["co2_ppm"] for p in pts)


def test_config_requires_admin_token(aws):
    seed(aws, 1)
    code, _ = call(aws, "PUT /devices/{id}/config", pathParameters={"id": "dev-1"},
                   headers={"x-admin-token": "wrong"}, body=json.dumps({"co2_alert_ppm": 1000}))
    assert code == 401


@pytest.mark.parametrize("body,status", [
    ({"co2_alert_ppm": 100}, 400), ({"interval_s": 1}, 400), ({"temp_max_c": "x"}, 400), ({}, 400),
])
def test_config_validation(aws, body, status):
    seed(aws, 1)
    code, _ = call(aws, "PUT /devices/{id}/config", pathParameters={"id": "dev-1"},
                   headers={"x-admin-token": "admin-secret"}, body=json.dumps(body))
    assert code == status


def test_config_updates_thresholds_and_device_shadow(aws):
    seed(aws, 1)
    iot = FakeIot()
    code, body = call(aws, "PUT /devices/{id}/config", iot=iot, pathParameters={"id": "dev-1"},
                      headers={"x-admin-token": "admin-secret"},
                      body=json.dumps({"co2_alert_ppm": 1000, "interval_s": 30, "temp_max_c": 28}))
    assert code == 200
    assert iot.updates == [("dev-1", {"state": {"desired": {"co2_alert_ppm": 1000, "interval_s": 30}}})]
    dev = aws[0].Table("airsense-devices").get_item(Key={"device_id": "dev-1"})["Item"]
    assert int(dev["co2_alert_ppm"]) == 1000 and float(dev["temp_max_c"]) == 28


def test_unknown_device_and_route(aws):
    code, _ = call(aws, "PUT /devices/{id}/config", pathParameters={"id": "nope"},
                   headers={"x-admin-token": "admin-secret"}, body=json.dumps({"interval_s": 30}))
    assert code == 404
    assert call(aws, "DELETE /everything")[0] == 404
