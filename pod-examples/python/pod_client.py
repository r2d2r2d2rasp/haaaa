"""Client di esempio per i POD (Arduino UNO Q, lato Linux/Python).

Configurazione via variabili d'ambiente:
    TS_BASE_URL   es. https://torinosegnala.vercel.app
    TS_API_KEY    chiave ts_live_...
Dipendenze: pip install requests
"""
import base64
import os
import time
from datetime import datetime, timezone

import requests

BASE = os.environ.get("TS_BASE_URL", "http://localhost:3000").rstrip("/")
KEY = os.environ["TS_API_KEY"]
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def send_report(category, lat, lon, confidence=1.0, photo_path=None, **metadata):
    body = {
        "category": category,
        "lat": lat,
        "lon": lon,
        "confidence": confidence,
        "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "metadata": metadata,
    }
    if photo_path:
        with open(photo_path, "rb") as f:
            body["photo_base64"] = base64.b64encode(f.read()).decode()
    r = requests.post(f"{BASE}/api/v1/reports", json=body, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def send_readings(metrics, lat=None, lon=None):
    """Misure dei sensori, es. {"temperature_c": 21.5, "co2_ppm": 480}. Vedi docs/POD_API.md per i nomi."""
    body = {"metrics": metrics, "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    if lat is not None and lon is not None:
        body.update(lat=lat, lon=lon)
    r = requests.post(f"{BASE}/api/v1/readings", json=body, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def send_heartbeat(lat=None, lon=None, battery=None, firmware=None):
    body = {k: v for k, v in dict(lat=lat, lon=lon, battery=battery, firmware=firmware).items() if v is not None}
    requests.post(f"{BASE}/api/v1/heartbeat", json=body, headers=HEADERS, timeout=15).raise_for_status()


def send_with_retry(*args, retries=5, **kwargs):
    """Riprova con backoff esponenziale se la rete è assente (utile sui bus)."""
    for attempt in range(retries):
        try:
            return send_report(*args, **kwargs)
        except requests.RequestException:
            time.sleep(2**attempt)
    return None


if __name__ == "__main__":
    # POD fisso (posizione configurata): semaforo in Piazza Castello, Torino
    LAT, LON = 45.0711, 7.6857
    send_heartbeat(LAT, LON, battery=92, firmware="demo-0.1")
    print(send_readings({"temperature_c": 21.5, "humidity_pct": 58, "co2_ppm": 480}, LAT, LON))
    print(send_report("rifiuti_abbandonati", LAT, LON, confidence=0.9, model="demo"))
