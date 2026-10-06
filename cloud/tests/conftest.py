import os
import sys
from pathlib import Path

os.environ.update(AWS_ACCESS_KEY_ID="testing", AWS_SECRET_ACCESS_KEY="testing", AWS_DEFAULT_REGION="us-east-1",
                  ADMIN_TOKEN="admin-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lambdas"))

import boto3  # noqa: E402
import pytest  # noqa: E402
from moto import mock_aws  # noqa: E402

import common  # noqa: E402


@pytest.fixture
def aws():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(TableName=common.READINGS_TABLE, BillingMode="PAY_PER_REQUEST",
                         KeySchema=[{"AttributeName": "device_id", "KeyType": "HASH"},
                                    {"AttributeName": "ts", "KeyType": "RANGE"}],
                         AttributeDefinitions=[{"AttributeName": "device_id", "AttributeType": "S"},
                                               {"AttributeName": "ts", "AttributeType": "N"}])
        ddb.create_table(TableName=common.DEVICES_TABLE, BillingMode="PAY_PER_REQUEST",
                         KeySchema=[{"AttributeName": "device_id", "KeyType": "HASH"}],
                         AttributeDefinitions=[{"AttributeName": "device_id", "AttributeType": "S"}])
        sns = boto3.client("sns", region_name="us-east-1")
        topic = sns.create_topic(Name="alerts")["TopicArn"]
        common.ALERT_TOPIC_ARN = topic
        import ingest
        ingest.ALERT_TOPIC_ARN = topic
        yield ddb, sns


NOW = 1_780_000_000


def reading(**kw):
    r = {"device_id": "dev-1", "topic_device": "dev-1", "ts": NOW, "temp_c": 22.5, "humidity_pct": 40.0,
         "pressure_hpa": 1012.0, "co2_ppm": 650, "tvoc_ppb": 20, "seq": 1, "air_quality": "good"}
    r.update(kw)
    return r
