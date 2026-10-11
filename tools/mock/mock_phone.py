"""Finto telefono: parla il protocollo contract/phone_link.v1.md.

Simula un bus che percorre via Po a ~29 km/h: track a 1 Hz, una foto ogni ~4 m,
una buca ogni 8 s (inviata due volte per provare la deduplica) e una frenata brusca.

    pip install websockets
    python tools/mock/mock_phone.py --url ws://127.0.0.1:8765/phone --seconds 20
"""
import argparse
import asyncio
import base64
import json
import math
import time

import websockets

FAKE_JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9").decode()
START = (45.06770, 7.69360)   # piazza Vittorio Veneto
HEADING = 300.0               # verso piazza Castello
SPEED = 8.0                   # m/s


def pos_at(t: float):
    d = SPEED * t
    lat = START[0] + d * math.cos(math.radians(HEADING)) / 111_320
    lon = START[1] + d * math.sin(math.radians(HEADING)) / (111_320 * math.cos(math.radians(START[0])))
    return lat, lon


async def main(url: str, seconds: int):
    seq = int(time.time() * 1000)
    acks, sent_events = set(), set()

    def msg(t, now_ms, extra):
        nonlocal seq
        seq += 1
        return {"v": 1, "t": t, "seq": seq, "device": "ph-mock0001", "ts_ms": now_ms, "ts_src": "gnss", **extra}

    async with websockets.connect(url, max_size=8 * 2**20) as ws:
        await ws.send(json.dumps({"v": 1, "t": "hello", "device": "ph-mock0001", "app_ver": "mock", "model": "mock", "android": 0}))

        async def reader():
            async for raw in ws:
                r = json.loads(raw)
                if r.get("t") == "ack":
                    acks.add(r["seq"])

        rtask = asyncio.create_task(reader())
        t0 = time.time()
        for i in range(seconds * 2):          # passo di 0,5 s
            t = i * 0.5
            now = int((t0 + t) * 1000)
            lat, lon = pos_at(t)
            p = {"lat": lat, "lon": lon, "acc_m": 4.5, "speed_mps": SPEED, "heading_deg": HEADING, "fix_age_ms": 50}
            if i % 2 == 0:
                await ws.send(json.dumps(msg("track", now, {**p, "imu": {"az_rms_ms2": 0.4, "decel_max_ms2": 0.3, "latacc_max_ms2": 0.2, "n": 100, "fwd_calibrated": True}})))
            await ws.send(json.dumps(msg("frame", now, {**p, "sharp": 80.0, "w": 640, "h": 360, "jpeg_b64": FAKE_JPEG})))
            if i % 16 == 8:                   # buca, inviata due volte (la seconda è un duplicato)
                ev = msg("event", now, {**p, "cls": "pothole", "src": "imu", "conf": 0.72, "severity": 2,
                                        "imu": {"p2p_ms2": 11.0, "thr_ms2": 9.0}, "frame_dt_ms": 900, "jpeg_b64": FAKE_JPEG})
                for _ in range(2):
                    await ws.send(json.dumps(ev))
                sent_events.add(ev["seq"])
            if i == 20:
                ev = msg("event", now, {**p, "cls": "harsh_braking", "src": "imu", "conf": 0.8, "severity": 2,
                                        "imu": {"peak_ms2": 2.9, "dur_ms": 700}})
                await ws.send(json.dumps(ev))
                sent_events.add(ev["seq"])
            await asyncio.sleep(0.5)
        await asyncio.sleep(1)
        rtask.cancel()
    missing = sent_events - acks
    print(f"eventi inviati: {len(sent_events)}, confermati: {len(sent_events & acks)}, senza ack: {sorted(missing)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://127.0.0.1:8765/phone")
    ap.add_argument("--seconds", type=int, default=20)
    a = ap.parse_args()
    asyncio.run(main(a.url, a.seconds))
