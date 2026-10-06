import pytest
from conftest import NOW, reading

import ingest


class RecordingSNS:
    def __init__(self, fail=0):
        self.fail, self.sent = fail, []

    def publish(self, **kw):
        if self.fail:
            self.fail -= 1
            raise ConnectionError("SNS unavailable")
        self.sent.append(kw["Subject"])


@pytest.mark.parametrize("bad", [
    {"co2_ppm": 5}, {"temp_c": 150}, {"humidity_pct": -1}, {"temp_c": "hot"}, {"temp_c": True},
    {"ts": NOW + 3600}, {"ts": NOW - 40 * 86400}, {"device_id": ""}, {"topic_device": "someone-else"},
])
def test_rejects_invalid_readings(aws, bad):
    ddb, _ = aws
    out = ingest.handler(reading(**bad), ddb=ddb, sns=RecordingSNS(), now=NOW)
    assert out["status"] == "rejected"
    assert ddb.Table("airsense-readings").scan()["Count"] == 0


def test_stores_reading_and_latest(aws):
    ddb, _ = aws
    assert ingest.handler(reading(), ddb=ddb, sns=RecordingSNS(), now=NOW)["latest"] is True
    item = ddb.Table("airsense-readings").get_item(Key={"device_id": "dev-1", "ts": NOW})["Item"]
    assert float(item["temp_c"]) == 22.5 and int(item["expires_at"]) == NOW + 30 * 86400
    dev = ddb.Table("airsense-devices").get_item(Key={"device_id": "dev-1"})["Item"]
    assert int(dev["last_ts"]) == NOW


def test_out_of_order_buffered_reading_does_not_overwrite_latest(aws):
    ddb, _ = aws
    ingest.handler(reading(ts=NOW, co2_ppm=700), ddb=ddb, sns=RecordingSNS(), now=NOW)
    out = ingest.handler(reading(ts=NOW - 60, co2_ppm=900), ddb=ddb, sns=RecordingSNS(), now=NOW)
    assert out["latest"] is False
    dev = ddb.Table("airsense-devices").get_item(Key={"device_id": "dev-1"})["Item"]
    assert int(dev["latest"]["co2_ppm"]) == 700
    assert ddb.Table("airsense-readings").scan()["Count"] == 2  # history still has both


def test_alert_raised_once_then_cleared_with_hysteresis(aws):
    ddb, _ = aws
    sns = RecordingSNS()
    for i, co2 in enumerate([800, 1300, 1400, 1150, 1050]):
        ingest.handler(reading(ts=NOW + i * 10, co2_ppm=co2), ddb=ddb, sns=sns, now=NOW + i * 10)
    # 1300 -> alert; 1400 still alerting (no repeat); 1150 is below 1200 but inside the
    # 100 ppm hysteresis band -> still alerting; 1050 -> resolved.
    assert [s.split(" ")[0] for s in sns.sent] == ["[ALERT]", "[RESOLVED]"]
    assert "CO2 1300 ppm" in sns.sent[0]


def test_old_buffered_breach_does_not_page(aws):
    ddb, _ = aws
    sns = RecordingSNS()
    out = ingest.handler(reading(ts=NOW - 3600, co2_ppm=2000), ddb=ddb, sns=sns, now=NOW)
    assert out["status"] == "stored" and sns.sent == []


def test_alert_is_retried_if_sns_fails(aws):
    ddb, _ = aws
    sns = RecordingSNS(fail=1)
    with pytest.raises(ConnectionError):
        ingest.handler(reading(co2_ppm=1500), ddb=ddb, sns=sns, now=NOW)
    dev = ddb.Table("airsense-devices").get_item(Key={"device_id": "dev-1"})["Item"]
    assert dev["alert_state"] == "ok"                 # rolled back, so the retry can alert
    ingest.handler(reading(co2_ppm=1500), ddb=ddb, sns=sns, now=NOW)  # Lambda's automatic retry
    assert len(sns.sent) == 1 and sns.sent[0].startswith("[ALERT]")


def test_custom_thresholds(aws):
    ddb, _ = aws
    ddb.Table("airsense-devices").put_item(Item={"device_id": "dev-1", "co2_alert_ppm": 900, "temp_max_c": 25})
    sns = RecordingSNS()
    ingest.handler(reading(co2_ppm=950, temp_c=26.0), ddb=ddb, sns=sns, now=NOW)
    assert "CO2 950" in sns.sent[0] and "temperature 26.0" in sns.sent[0]
