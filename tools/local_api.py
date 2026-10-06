"""Run the REAL Lambda code locally against an in-memory DynamoDB/SNS (moto), so the
dashboard and simulator work with no AWS account.  http://localhost:8001

  pip install -r tools/requirements.txt && python tools/local_api.py
"""
import json
import os
import sys
from pathlib import Path

os.environ.update(AWS_ACCESS_KEY_ID="local", AWS_SECRET_ACCESS_KEY="local", AWS_DEFAULT_REGION="us-east-1")
os.environ.setdefault("ADMIN_TOKEN", "local-admin")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cloud" / "lambdas"))

import boto3  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, Request, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from moto import mock_aws  # noqa: E402

mock = mock_aws()
mock.start()
import api  # noqa: E402
import common  # noqa: E402
import ingest  # noqa: E402

ddb = boto3.resource("dynamodb")
ddb.create_table(TableName=common.READINGS_TABLE, BillingMode="PAY_PER_REQUEST",
                 KeySchema=[{"AttributeName": "device_id", "KeyType": "HASH"}, {"AttributeName": "ts", "KeyType": "RANGE"}],
                 AttributeDefinitions=[{"AttributeName": "device_id", "AttributeType": "S"},
                                       {"AttributeName": "ts", "AttributeType": "N"}])
ddb.create_table(TableName=common.DEVICES_TABLE, BillingMode="PAY_PER_REQUEST",
                 KeySchema=[{"AttributeName": "device_id", "KeyType": "HASH"}],
                 AttributeDefinitions=[{"AttributeName": "device_id", "AttributeType": "S"}])
sns = boto3.client("sns")
ingest.ALERT_TOPIC_ARN = sns.create_topic(Name="alerts")["TopicArn"]
api.ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]


class PrintSns:
    def publish(self, **kw):
        print(f"\n*** SNS email: {kw['Subject']}\n")


class PrintIot:
    def update_thing_shadow(self, thingName, payload):
        print(f"*** shadow desired for {thingName}: {payload.decode()}")


app = FastAPI(title="AirSense local API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def as_http(out: dict) -> Response:
    return Response(out["body"], status_code=out["statusCode"], media_type="application/json")


@app.post("/ingest")  # stands in for the AWS IoT rule
async def post_ingest(req: Request):
    evt = await req.json()
    evt.setdefault("topic_device", evt.get("device_id"))
    return ingest.handler(evt, ddb=ddb, sns=PrintSns())


@app.get("/devices")
def devices():
    return as_http(api.handler({"routeKey": "GET /devices"}, ddb=ddb))


@app.get("/devices/{device_id}/readings")
def readings(device_id: str, minutes: int = 60):
    return as_http(api.handler({"routeKey": "GET /devices/{id}/readings", "pathParameters": {"id": device_id},
                                "queryStringParameters": {"minutes": str(minutes)}}, ddb=ddb))


@app.put("/devices/{device_id}/config")
async def config(device_id: str, req: Request):
    return as_http(api.handler({"routeKey": "PUT /devices/{id}/config", "pathParameters": {"id": device_id},
                                "headers": {k.lower(): v for k, v in req.headers.items()},
                                "body": (await req.body()).decode()}, ddb=ddb, iot=PrintIot()))


if __name__ == "__main__":
    print(f"Admin token for config changes: {os.environ['ADMIN_TOKEN']}")
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
