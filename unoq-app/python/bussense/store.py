"""Archivio locale: riga BS1, giornale JSONL, SQLite (WAL), media oscurati.

Un solo processo scrive su ogni file (regola SQLite WAL).
"""
import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS observation(
  id TEXT PRIMARY KEY, seq INTEGER UNIQUE NOT NULL, device_id TEXT NOT NULL, phone_id TEXT,
  ts_utc TEXT NOT NULL, ts_src TEXT NOT NULL CHECK(ts_src IN('gnss','ntp','phone','unsynced')),
  obs_lat REAL, obs_lon REAL, acc_m REAL, speed_mps REAL, heading_deg REAL, fix_age_ms INTEGER,
  tgt_lat REAL, tgt_lon REAL,
  type TEXT NOT NULL, src TEXT NOT NULL, conf REAL NOT NULL CHECK(conf BETWEEN 0 AND 1),
  severity INTEGER, model TEXT, media_sha256 TEXT, detail_json TEXT, env_json TEXT, issue_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS obs_type_ts ON observation(type, ts_utc);
CREATE TABLE IF NOT EXISTS media(
  sha256 TEXT PRIMARY KEY, path TEXT NOT NULL,
  redacted INTEGER NOT NULL CHECK(redacted = 1),
  created_at TEXT NOT NULL, synced_at TEXT
);
"""

TS_DDL = """
CREATE TABLE IF NOT EXISTS ts_1hz(
  t_ms INTEGER PRIMARY KEY, ts_src TEXT, phone_id TEXT,
  lat REAL, lon REAL, acc_m REAL, speed_mps REAL, heading_deg REAL,
  co2_ppm REAL, voc_idx REAL, t_c REAL, rh_pct REAL,
  az_rms_ms2 REAL, decel_max_ms2 REAL, latacc_max_ms2 REAL, flags INTEGER NOT NULL DEFAULT 0
);
"""

TS_COLS = ["t_ms", "ts_src", "phone_id", "lat", "lon", "acc_m", "speed_mps", "heading_deg",
           "co2_ppm", "voc_idx", "t_c", "rh_pct", "az_rms_ms2", "decel_max_ms2", "latacc_max_ms2", "flags"]

# bit della colonna flags (vedi PIANO.md 5.5)
F_GPS_POOR, F_STATIONARY, F_WARMUP, F_STALE, F_PRIVACY, F_UNSYNCED = 1, 2, 4, 8, 16, 32


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def uuid7() -> str:
    ms = time.time_ns() // 1_000_000
    r = int.from_bytes(os.urandom(10), "big")
    val = ((ms & (2**48 - 1)) << 80) | (0x7 << 76) | (((r >> 62) & 0xFFF) << 64) | (0b10 << 62) | (r & (2**62 - 1))
    return str(uuid.UUID(int=val))


def _fmt(x, nd=6):
    return "" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


class Store:
    def __init__(self, root: str, device_id: str = "unoq-01"):
        self.root = Path(root)
        self.device_id = device_id
        for d in ("reports", "journal", "media"):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.ev = sqlite3.connect(self.root / "events.db", check_same_thread=False)
        self.ev.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;" + EVENTS_DDL)
        self.ts = sqlite3.connect(self.root / "ts.db", check_same_thread=False)
        self.ts.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;" + TS_DDL)
        self.seq = (self.ev.execute("SELECT MAX(seq) FROM observation").fetchone()[0] or 0)
        self._ts_buf: list[tuple] = []
        self._ts_flushed = time.monotonic()

    # ---------- osservazioni (eventi) ----------
    def add_observation(self, o: dict) -> dict:
        """o: type, src, conf, ts_ms, ts_src e, se presenti, lat/lon/acc_m/speed_mps/heading_deg,
        severity, model, phone_id, detail, env, media_sha256. Restituisce il record completo."""
        with self.lock:
            self.seq += 1
            rec = {
                "schema": "bs.obs.v1", "id": uuid7(), "seq": self.seq, "device_id": self.device_id,
                "phone_id": o.get("phone_id"), "ts": iso(o["ts_ms"]), "ts_src": o.get("ts_src", "unsynced"),
                "obs": {k: o.get(k) for k in ("lat", "lon", "acc_m", "speed_mps", "heading_deg", "fix_age_ms")},
                # eventi IMU: l'oggetto è sotto il bus; per la visione andrà proiettato in avanti
                "tgt": {"lat": o.get("tgt_lat", o.get("lat")), "lon": o.get("tgt_lon", o.get("lon"))},
                "type": o["type"], "src": o["src"], "conf": round(float(o["conf"]), 3),
                "severity": o.get("severity"), "model": o.get("model"),
                "detail": o.get("detail") or {}, "env": o.get("env") or {},
                "media_sha256": o.get("media_sha256"),
            }
            self._append_report_line(rec)
            self._append_jsonl(rec)
            self.ev.execute(
                "INSERT INTO observation VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rec["id"], rec["seq"], rec["device_id"], rec["phone_id"], rec["ts"], rec["ts_src"],
                 rec["obs"]["lat"], rec["obs"]["lon"], rec["obs"]["acc_m"], rec["obs"]["speed_mps"],
                 rec["obs"]["heading_deg"], rec["obs"]["fix_age_ms"], rec["tgt"]["lat"], rec["tgt"]["lon"],
                 rec["type"], rec["src"], rec["conf"], rec["severity"], rec["model"], rec["media_sha256"],
                 json.dumps(rec["detail"]), json.dumps(rec["env"]), None, iso(int(time.time() * 1000))))
            self.ev.commit()
            return rec

    def report_line(self, rec: dict) -> str:
        """La riga BS1 (PIANO.md 5.2)."""
        o = rec["obs"]
        return ";".join([
            "BS1", rec["ts"], rec["ts_src"], _fmt(rec["tgt"]["lat"]), _fmt(rec["tgt"]["lon"]),
            _fmt(o["acc_m"], 1), _fmt(o["speed_mps"], 1), _fmt(o["heading_deg"], 0),
            rec["type"], rec["src"], _fmt(rec["conf"], 2), _fmt(rec["severity"]),
            rec["model"] or "", rec["device_id"], rec["id"]])

    def _append_report_line(self, rec: dict):
        day = rec["ts"][:10].replace("-", "")
        self._append(self.root / "reports" / f"reports-{day}.log", self.report_line(rec))

    def _append_jsonl(self, rec: dict):
        day = rec["ts"][:10].replace("-", "")
        self._append(self.root / "journal" / f"obs-{day}.jsonl", json.dumps(rec, separators=(",", ":")))

    @staticmethod
    def _append(path: Path, line: str):
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    # ---------- media (solo immagini GIÀ oscurate) ----------
    def save_redacted_media(self, jpeg: bytes, ts_ms: int) -> str:
        sha = hashlib.sha256(jpeg).hexdigest()
        rel = Path("media") / iso(ts_ms)[:10] / f"{sha}.jpg"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            f.write(jpeg)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # prima il file, poi la riga nel DB
        with self.lock:
            self.ev.execute("INSERT OR IGNORE INTO media VALUES(?,?,1,?,NULL)", (sha, str(rel), iso(ts_ms)))
            self.ev.commit()
        return sha

    # ---------- serie temporale 1 Hz ----------
    def ts_row(self, row: dict):
        with self.lock:
            self._ts_buf.append(tuple(row.get(c) for c in TS_COLS))
        self.flush_if_due()

    def flush_if_due(self, every_s: float = 10.0):
        if time.monotonic() - self._ts_flushed < every_s:
            return
        with self.lock:
            rows, self._ts_buf = self._ts_buf, []
            self._ts_flushed = time.monotonic()
            if rows:
                self.ts.executemany(
                    f"INSERT OR REPLACE INTO ts_1hz({','.join(TS_COLS)}) VALUES({','.join('?' * len(TS_COLS))})", rows)
                self.ts.commit()

    def close(self):
        self.flush_if_due(every_s=0)
        self.ev.close()
        self.ts.close()
