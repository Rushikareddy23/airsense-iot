"""Device simulator: realistic indoor-air readings without hardware.

  # to the local dev API (no AWS needed):
  python tools/simulate.py --local --devices 3 --backfill-hours 6
  # to real AWS IoT Core with a device certificate:
  python tools/simulate.py --endpoint xxxx-ats.iot.us-east-1.amazonaws.com \
      --cert certs/device.pem.crt --key certs/private.pem.key --ca certs/AmazonRootCA1.pem --device airsense-01

Model: temperature follows a daily cycle; CO2 rises while a room is "occupied" (people
exhale CO2) and decays toward outdoor level (~420 ppm) when ventilated.
"""
import argparse
import json
import math
import random
import time


class Room:
    def __init__(self, device_id: str, seed: int, force_occupants: int | None = None):
        self.force_occupants = force_occupants
        self.device_id = device_id
        self.rng = random.Random(seed)
        self.co2 = 450.0
        self.occupants = 0
        self.seq = 0

    def step(self, ts: int, dt: float) -> dict:
        hour = (ts % 86400) / 3600
        working = 8 <= hour < 18
        if self.force_occupants is not None:
            self.occupants = self.force_occupants
        elif self.rng.random() < dt / 1800:  # occupancy changes about every 30 min
            self.occupants = self.rng.randint(2, 8) if working else self.rng.randint(0, 1)
        # Mass balance: generation from people minus ventilation toward outdoor air.
        gen = self.occupants * 0.3 * dt / 60 * 20
        self.co2 += gen - (self.co2 - 420) * (1 - math.exp(-dt / 2400))
        temp = 21.5 + 2.0 * math.sin((hour - 9) / 24 * 2 * math.pi) + 0.15 * self.occupants
        self.seq += 1
        return {
            "device_id": self.device_id, "seq": self.seq, "ts": ts,
            "temp_c": round(temp + self.rng.gauss(0, 0.05), 2),
            "humidity_pct": round(42 + 6 * math.sin(hour / 24 * 2 * math.pi) + self.rng.gauss(0, 0.3), 1),
            "pressure_hpa": round(1013 + 3 * math.sin(ts / 86400 / 3) + self.rng.gauss(0, 0.05), 1),
            "co2_ppm": int(max(400, self.co2 + self.rng.gauss(0, 8))),
            "tvoc_ppb": int(max(0, 30 + 8 * self.occupants + self.rng.gauss(0, 5))),
        }


def local_sender(url):
    import urllib.request

    def send(msg):
        req = urllib.request.Request(f"{url}/ingest", data=json.dumps(msg).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()
    return send


def mqtt_sender(a):
    import paho.mqtt.client as mqtt
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=a.device)
    c.tls_set(ca_certs=a.ca, certfile=a.cert, keyfile=a.key)
    c.connect(a.endpoint, 8883, keepalive=60)
    c.loop_start()

    def send(msg):
        c.publish(f"airsense/{msg['device_id']}/telemetry", json.dumps(msg), qos=1).wait_for_publish(10)
    return send


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--url", default="http://localhost:8001")
    ap.add_argument("--devices", type=int, default=1)
    ap.add_argument("--device", default="airsense-01")
    ap.add_argument("--interval", type=float, default=10)
    ap.add_argument("--crowded", action="store_true", help="10 people in room-1: CO2 climbs past the alert level")
    ap.add_argument("--backfill-hours", type=float, default=0, help="send past data first (fast)")
    ap.add_argument("--endpoint"), ap.add_argument("--cert"), ap.add_argument("--key"), ap.add_argument("--ca")
    a = ap.parse_args()
    send = local_sender(a.url) if a.local else mqtt_sender(a)
    ids = [f"room-{i + 1}" for i in range(a.devices)] if a.local else [a.device]
    rooms = [Room(d, i, 10 if a.crowded and i == 0 else None) for i, d in enumerate(ids)]

    now = int(time.time())
    if a.backfill_hours:
        step = 60
        for ts in range(now - int(a.backfill_hours * 3600), now, step):
            for r in rooms:
                send(r.step(ts, step))
        print(f"backfilled {a.backfill_hours} h for {len(rooms)} device(s)")
    while True:
        for r in rooms:
            msg = r.step(int(time.time()), a.interval)
            send(msg)
            print(json.dumps(msg))
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
