"""Server WebSocket che riceve i dati dal telefono (protocollo contract/phone_link.v1.md)."""
import asyncio
import base64
import json
import logging
import math
import os
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

import websockets

from . import privacy
from .store import F_GPS_POOR, F_STALE, F_STATIONARY, F_UNSYNCED, Store

log = logging.getLogger("bussense.rx")

# raggio (m) e finestra (ms) entro cui due eventi dello stesso tipo sono lo stesso evento
DEDUP = {"pothole": (8, 3000), "harsh_braking": (25, 5000), "swerve": (25, 5000)}
EVENT_TYPES = set(DEDUP)
MAX_ACC_M = 15.0  # oltre questa accuratezza GPS l'evento si salva ma non va in mappa (flag nel detail)


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _ram_dir() -> Path:
    base = Path("/dev/shm") if Path("/dev/shm").is_dir() else Path(tempfile.gettempdir())
    d = base / "bussense"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Receiver:
    def __init__(self, store: Store, host: str = "0.0.0.0", port: int = 8765, on_frame=None,
                 debug_save_frames: bool = False, debug_frames_max: int = 300):
        self.store, self.host, self.port = store, host, port
        self.on_frame = on_frame  # callback(jpeg: bytes, meta: dict) -> per la visione (R2)
        self.on_report = None     # callback(rec: dict) dopo ogni segnalazione salvata -> invio a TorinoSegnala
        self.fix_provider = None  # callable -> fix di riserva (modulo GPS / posizione fissa) se manca il telefono
        self.ram = _ram_dir()
        self.last_fix: dict | None = None
        self.last_fix_mono = 0.0  # time.monotonic() all'arrivo di last_fix
        self.env: dict = {}
        self._env_ts = 0.0
        self._recent: deque = deque(maxlen=200)  # (ts_ms, type, lat, lon)
        self._seen: deque = deque(maxlen=2000)   # (device, seq) degli eventi già ricevuti
        self.counters = {"track": 0, "frame": 0, "event": 0, "duplicate": 0, "bad": 0}
        # SOLO DEBUG: scrive ogni "frame" anche su disco (non oscurato). Di default spento:
        # in produzione le foto "frame" restano solo in RAM (privacy, vedi _frame).
        self.debug_save_frames = debug_save_frames
        self.debug_frames_max = debug_frames_max
        self._debug_frame_files: deque = deque(maxlen=debug_frames_max)
        if debug_save_frames:
            self.debug_dir = self.store.root / "debug_frames"
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            log.warning("BUSSENSE_DEBUG_SAVE_FRAMES attivo: le foto 'frame' vengono salvate su disco in %s "
                        "(solo per collaudo, NON lasciare attivo in produzione)", self.debug_dir)

    # ---------- dati ambientali dal MCU (via Bridge) ----------
    def update_env(self, **values):
        self.env.update({k: v for k, v in values.items() if v is not None})
        self._env_ts = time.time()

    def env_snapshot(self) -> dict:
        return dict(self.env) if time.time() - self._env_ts < 15 else {}

    # ---------- server ----------
    def start_in_thread(self):
        threading.Thread(target=lambda: asyncio.run(self.serve_forever()), name="rx", daemon=True).start()

    async def serve_forever(self):
        async with websockets.serve(self._handler, self.host, self.port, max_size=8 * 2**20, ping_interval=20):
            log.info("in ascolto su ws://%s:%d/phone", self.host, self.port)
            await asyncio.Future()

    async def _handler(self, ws):
        log.info("telefono collegato da %s", ws.remote_address)
        try:
            async for raw in ws:
                try:
                    reply = self.handle(json.loads(raw))
                except Exception:
                    self.counters["bad"] += 1
                    log.exception("messaggio non valido")
                    continue
                if reply:
                    await ws.send(json.dumps(reply))
        except websockets.ConnectionClosed:
            pass
        log.info("telefono scollegato")

    # ---------- logica (sincrona, testabile senza rete) ----------
    def handle(self, m: dict) -> dict | None:
        t = m.get("t")
        if t == "hello":
            log.info("hello: %s", {k: m.get(k) for k in ("device", "model", "android", "app_ver")})
            return {"t": "hello_ack", "server": "bussense-unoq", "v": 1}
        if t == "track":
            self._track(m)
        elif t == "frame":
            self._frame(m)
        elif t == "event":
            self._event(m)
            return {"t": "ack", "seq": m["seq"]}
        else:
            self.counters["bad"] += 1
        return None

    def _track(self, m: dict):
        self.counters["track"] += 1
        self.last_fix = m
        self.last_fix_mono = time.monotonic()
        flags = 0
        if m.get("acc_m") is None or m["acc_m"] > MAX_ACC_M:
            flags |= F_GPS_POOR
        if (m.get("speed_mps") or 0) < 0.5:
            flags |= F_STATIONARY
        if m.get("ts_src") != "gnss":
            flags |= F_UNSYNCED
        env = self.env_snapshot()
        if self.env and not env:
            flags |= F_STALE
        imu = m.get("imu") or {}
        self.store.ts_row({
            "t_ms": m["ts_ms"], "ts_src": m.get("ts_src"), "phone_id": m.get("device"),
            **{k: m.get(k) for k in ("lat", "lon", "acc_m", "speed_mps", "heading_deg")},
            "co2_ppm": env.get("co2_ppm"), "voc_idx": env.get("voc_idx"), "t_c": env.get("t_c"), "rh_pct": env.get("rh_pct"),
            "az_rms_ms2": imu.get("az_rms_ms2"), "decel_max_ms2": imu.get("decel_max_ms2"),
            "latacc_max_ms2": imu.get("latacc_max_ms2"), "flags": flags,
        })

    def _frame(self, m: dict):
        """Foto per la visione: SOLO in RAM, mai su disco (privacy) -- salvo debug_save_frames."""
        self.counters["frame"] += 1
        jpeg = base64.b64decode(m["jpeg_b64"])
        tmp = self.ram / "latest.tmp"
        tmp.write_bytes(jpeg)
        os.replace(tmp, self.ram / "latest.jpg")
        if self.debug_save_frames:
            self._save_debug_frame(jpeg, m)
        if self.on_frame:
            meta = {k: v for k, v in m.items() if k != "jpeg_b64"}
            self.on_frame(jpeg, meta)

    def _save_debug_frame(self, jpeg: bytes, m: dict):
        """SOLO DEBUG: scrive la foto su disco, non oscurata, con rotazione a debug_frames_max file."""
        name = f"{m.get('ts_ms', 0)}_{m.get('device', 'na')}_{m.get('seq', 0)}.jpg"
        path = self.debug_dir / name
        path.write_bytes(jpeg)
        evicted = None
        if len(self._debug_frame_files) >= self.debug_frames_max:
            evicted = self._debug_frame_files[0]   # il deque lo scarterà da solo con l'append
        self._debug_frame_files.append(path)
        if evicted is not None:
            evicted.unlink(missing_ok=True)

    def _event(self, m: dict):
        if m.get("cls") not in EVENT_TYPES:
            self.counters["bad"] += 1
            return
        if self._is_duplicate(m):
            self.counters["duplicate"] += 1
            log.info("duplicato scartato: %s seq=%s", m["cls"], m["seq"])
            return
        media = None
        if m.get("jpeg_b64"):
            red = privacy.redact(base64.b64decode(m["jpeg_b64"]))  # fail-closed: None = niente immagine
            if red is not None:
                media = self.store.save_redacted_media(red, m["ts_ms"])
        detail = dict(m.get("imu") or {})
        if m.get("acc_m") is None or m["acc_m"] > MAX_ACC_M:
            detail["gps_poor"] = True
        rec = self.report(type=m["cls"], src=m.get("src", "imu"), conf=m["conf"], ts_ms=m["ts_ms"],
                          ts_src=m.get("ts_src"), severity=m.get("severity"), model="phone-imu-v1",
                          phone_id=m.get("device"), detail=detail, media_sha256=media,
                          **{k: m.get(k) for k in ("lat", "lon", "acc_m", "speed_mps", "heading_deg", "fix_age_ms")})
        self.counters["event"] += 1
        log.info("EVENTO %s", self.store.report_line(rec))

    def report(self, **o) -> dict:
        """Punto d'ingresso unico per salvare una segnalazione (usato anche dalla visione)."""
        o.setdefault("env", self.env_snapshot())
        if o.get("lat") is None:  # evento senza fix: usa l'ultimo fix noto, poi la fonte di riserva
            fix = self.last_fix if self.last_fix and self.last_fix.get("lat") is not None else None
            if fix is None and self.fix_provider:
                fix = self.fix_provider()
            if fix:
                for k in ("lat", "lon", "acc_m", "speed_mps", "heading_deg"):
                    o[k] = fix.get(k)
        rec = self.store.add_observation(o)
        if o.get("lat") is not None:
            self._recent.append((o["ts_ms"], o["type"], o["lat"], o["lon"]))
        if self.on_report:
            try:
                self.on_report(rec)
            except Exception:
                log.exception("on_report fallito (la segnalazione resta salvata in locale)")
        return rec

    def _is_duplicate(self, m: dict) -> bool:
        key = (m.get("device"), m.get("seq"))  # reinvio dopo una riconnessione
        if key in self._seen:
            return True
        self._seen.append(key)
        if m.get("lat") is None:
            return False
        radius, window = DEDUP[m["cls"]]
        for ts, typ, lat, lon in self._recent:
            if typ == m["cls"] and abs(m["ts_ms"] - ts) <= window and haversine_m(lat, lon, m["lat"], m["lon"]) <= radius:
                return True
        return False
