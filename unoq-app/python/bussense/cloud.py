"""Invio dei dati alla piattaforma TorinoSegnala (API v1 per i POD, docs/POD_API.md).

Tutto passa da una coda su disco (outbox.db): una segnalazione o una misura non si perde se manca
la rete o se la chiave API non c'è ancora. Un thread la svuota appena può.

- segnalazioni -> POST /api/v1/reports   (una per richiesta, solo i tipi in TYPE_TO_CATEGORY)
- misure       -> POST /api/v1/readings  (lotti fino a 100, campionate ogni READINGS_S secondi)
- battito      -> POST /api/v1/heartbeat (ogni HEARTBEAT_S secondi, NON in coda: conta solo l'ultimo)

Configurazione (variabili d'ambiente):
    TS_API_KEY        chiave ts_live_... creata dalla Console IT (senza: si accoda e basta)
    TS_BASE_URL       default https://torinosegnala.vercel.app
    TS_HEARTBEAT_S    default 60
    TS_READINGS_S     default 60
    BUSSENSE_FW       versione firmware mostrata nella Console IT

Uso a riga di comando (dalla cartella python/):
    python -m bussense.cloud status      # contenuto della coda
    python -m bussense.cloud ping        # un battito di prova, stampa la risposta
"""
import json
import logging
import math
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("bussense.cloud")

DEFAULT_BASE = "https://torinosegnala.vercel.app"

# tipo di evento BusSense -> categoria della piattaforma. Frenate e sterzate non sono segnalazioni.
TYPE_TO_CATEGORY = {
    "pothole": "buca",
    "overflowing_bin": "cassonetto_pieno",
    "bulky_waste": "rifiuti_abbandonati",
}

# dati ambientali del MCU (rx.env) -> nomi metrica della piattaforma
ENV_TO_METRIC = {
    "t_c": "temperature_c",
    "rh_pct": "humidity_pct",
    "co2_ppm": "co2_ppm",
    "voc_idx": "voc_index",
    "voc_raw": "voc_raw",
}

# stessa area accettata dal server (web/app/api/v1/reports/route.ts): fuori, la richiesta è rifiutata
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = 44.9, 45.2, 7.45, 7.9
MAX_PHOTO_BYTES = 5 * 2**20
BATCH_MAX = 100

OUTBOX_DDL = """
CREATE TABLE IF NOT EXISTS outbox(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK(kind IN('report','reading')),
  ref TEXT UNIQUE,                 -- id dell'osservazione (evita doppi accodamenti)
  payload TEXT NOT NULL,
  created_ms INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','sent','rejected')),
  attempts INTEGER NOT NULL DEFAULT 0,
  next_try_ms INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  response TEXT,
  done_ms INTEGER
);
CREATE INDEX IF NOT EXISTS outbox_due ON outbox(status, kind, next_try_ms);
"""


def in_turin(lat, lon) -> bool:
    return (isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            and LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _clock_ok() -> bool:
    """La UNO Q senza rete può partire con l'orologio indietro: in quel caso non mandiamo captured_at."""
    return time.time() > 1_735_689_600  # 2025-01-01


class ApiError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status, self.body = status, body


class Client:
    """Chiamate HTTP alla piattaforma (solo libreria standard: niente pip in più sulla UNO Q)."""

    def __init__(self, base_url: str, api_key: str | None, timeout: float = 15.0):
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.timeout = timeout

    def post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            self.base + path, data=json.dumps(body, separators=(",", ":")).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
                     "User-Agent": "bussense-unoq/1"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, e.read().decode("utf-8", "replace")) from None


class Outbox:
    """Coda persistente in SQLite. Più thread accodano, uno solo invia."""

    def __init__(self, path: Path):
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;" + OUTBOX_DDL)

    def add(self, kind: str, payload: dict, ref: str | None = None):
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO outbox(kind, ref, payload, created_ms) VALUES(?,?,?,?)",
                            (kind, ref, json.dumps(payload, separators=(",", ":")), _now_ms()))
            self.db.commit()

    def due(self, kind: str, limit: int) -> list[tuple[int, dict, int]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT id, payload, attempts FROM outbox WHERE status='pending' AND kind=? AND next_try_ms<=? "
                "ORDER BY id LIMIT ?", (kind, _now_ms(), limit)).fetchall()
        return [(i, json.loads(p), a) for i, p, a in rows]

    def mark(self, ids: list[int], status: str, response=None, error: str | None = None):
        with self.lock:
            self.db.executemany(
                "UPDATE outbox SET status=?, response=?, last_error=?, done_ms=?, attempts=attempts+1 WHERE id=?",
                [(status, None if response is None else json.dumps(response), error, _now_ms(), i) for i in ids])
            self.db.commit()

    def retry_later(self, ids: list[int], attempts: int, error: str):
        delay_s = min(5 * 2 ** attempts, 600)  # 5 s, 10 s, 20 s ... fino a 10 minuti
        with self.lock:
            self.db.executemany(
                "UPDATE outbox SET attempts=attempts+1, next_try_ms=?, last_error=? WHERE id=?",
                [(_now_ms() + delay_s * 1000, error[:300], i) for i in ids])
            self.db.commit()

    def counts(self) -> dict:
        with self.lock:
            rows = self.db.execute("SELECT kind, status, COUNT(*) FROM outbox GROUP BY kind, status").fetchall()
        return {f"{k}_{s}": n for k, s, n in rows}

    def prune(self, keep_days: int = 7):
        with self.lock:
            self.db.execute("DELETE FROM outbox WHERE status!='pending' AND done_ms<?",
                            (_now_ms() - keep_days * 86_400_000,))
            self.db.commit()

    def close(self):
        with self.lock:
            self.db.close()


class Uploader:
    """Collega la UNO Q a TorinoSegnala.

    rx:       il Receiver (per rx.env_snapshot())
    position: callable -> dict con lat/lon/acc_m/speed_mps/heading_deg/src, oppure None
    """

    def __init__(self, data_root: str | Path, rx=None, position=None, base_url: str | None = None,
                 api_key: str | None = None, heartbeat_s: float | None = None, readings_s: float | None = None,
                 firmware: str | None = None):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.rx, self.position = rx, position
        self.client = Client(base_url or os.environ.get("TS_BASE_URL") or DEFAULT_BASE,
                             api_key if api_key is not None else os.environ.get("TS_API_KEY"))
        self.heartbeat_s = heartbeat_s or float(os.environ.get("TS_HEARTBEAT_S", "60"))
        self.readings_s = readings_s or float(os.environ.get("TS_READINGS_S", "60"))
        self.firmware = firmware or os.environ.get("BUSSENSE_FW", "bussense-unoq-0.1")
        self.outbox = Outbox(self.root / "outbox.db")
        self.stats = {"sent_reports": 0, "sent_readings": 0, "rejected": 0, "heartbeats": 0, "errors": 0}
        self.online: bool | None = None       # None = mai provato
        self.last_error: str | None = None
        self._pause_until = 0.0               # dopo un errore di rete o 401 non martelliamo il server
        self._last_hb = self._last_rd = self._last_prune = 0.0
        self._stop = threading.Event()
        self._warned_no_key = False

    # ---------- dal resto dell'app ----------
    def on_report(self, rec: dict):
        """Callback per rx.on_report: riceve il record bs.obs.v1 appena salvato da Store."""
        category = TYPE_TO_CATEGORY.get(rec.get("type"))
        if category is None:
            return
        lat, lon = rec["tgt"]["lat"], rec["tgt"]["lon"]
        if not in_turin(lat, lon):
            log.info("segnalazione %s non inviata: posizione %s,%s assente o fuori Torino", rec["id"], lat, lon)
            return
        o = rec["obs"]
        src = {"vision": "visione", "imu": "sensori di movimento"}.get(rec.get("src"), rec.get("src"))
        payload = {
            "category": category, "lat": lat, "lon": lon,
            "confidence": max(0.0, min(1.0, float(rec["conf"]))),
            "description": f"Rilevato automaticamente da BusSense ({src}).",
            "metadata": {
                "bussense_id": rec["id"], "seq": rec["seq"], "device_id": rec["device_id"],
                "type": rec["type"], "src": rec["src"], "model": rec.get("model"), "severity": rec.get("severity"),
                "acc_m": o.get("acc_m"), "speed_mps": o.get("speed_mps"), "heading_deg": o.get("heading_deg"),
                "ts_src": rec.get("ts_src"), "detail": rec.get("detail") or {}, "env": rec.get("env") or {},
            },
        }
        if rec.get("ts_src") in ("gnss", "ntp", "phone"):
            payload["captured_at"] = rec["ts"]
        if rec.get("media_sha256"):  # solo immagini già oscurate (privacy.redact)
            payload["media"] = str(Path("media") / rec["ts"][:10] / f"{rec['media_sha256']}.jpg")
        self.outbox.add("report", payload, ref=rec["id"])

    def sample_readings(self):
        metrics = self._metrics()
        if not metrics:
            return
        r: dict = {"metrics": metrics}
        if _clock_ok():
            r["captured_at"] = _iso_ms(_now_ms())
        fix = self._fix()
        if fix and in_turin(fix.get("lat"), fix.get("lon")):
            r.update(lat=fix["lat"], lon=fix["lon"])
        self.outbox.add("reading", r)

    # ---------- thread ----------
    def start_in_thread(self):
        threading.Thread(target=self._run, name="cloud", daemon=True).start()
        if self.client.key:
            log.info("TorinoSegnala: invio a %s", self.client.base)
        else:
            log.warning("TorinoSegnala: TS_API_KEY non impostata, i dati restano in coda in %s",
                        self.root / "outbox.db")

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                self.stats["errors"] += 1
                log.exception("errore nel ciclo di invio")
            self._stop.wait(2)

    def tick(self):
        """Un giro di lavoro: campiona, invia battito, svuota un po' di coda. Testabile senza thread."""
        now = time.monotonic()
        if now - self._last_rd >= self.readings_s:
            self._last_rd = now
            self.sample_readings()
        if now - self._last_prune >= 3600:
            self._last_prune = now
            self.outbox.prune()
        if not self.client.key:
            if not self._warned_no_key:
                self._warned_no_key = True
                log.info("TorinoSegnala: nessuna chiave, invio sospeso (coda: %s)", self.outbox.counts())
            return
        if now - self._last_hb >= self.heartbeat_s and not self._paused():
            self._last_hb = now
            self.send_heartbeat()
        if not self._paused():
            self._flush_reports()
        if not self._paused():
            self._flush_readings()

    def _paused(self) -> bool:
        return time.monotonic() < self._pause_until

    # ---------- invii ----------
    def send_heartbeat(self) -> dict | None:
        body: dict = {"firmware": self.firmware}
        fix = self._fix()
        if fix and fix.get("lat") is not None:
            body.update(lat=fix["lat"], lon=fix["lon"])
        try:
            res = self.client.post("/api/v1/heartbeat", body)
            self._ok()
            self.stats["heartbeats"] += 1
            return res
        except Exception as e:
            self._fail(e)
            return None

    def _flush_reports(self, max_per_tick: int = 5):
        for row_id, payload, attempts in self.outbox.due("report", max_per_tick):
            body = dict(payload)
            media = body.pop("media", None)
            if media:
                photo = self._photo_b64(media)
                if photo:
                    body["photo_base64"] = photo
            try:
                res = self.client.post("/api/v1/reports", body)
            except Exception as e:
                if not self._handle_error([row_id], attempts, e):
                    return
                continue
            self._ok()
            self.outbox.mark([row_id], "sent", res)
            self.stats["sent_reports"] += 1
            log.info("TorinoSegnala: segnalazione %s inviata -> %s", payload["category"], res)

    def _flush_readings(self):
        rows = self.outbox.due("reading", BATCH_MAX)
        if not rows:
            return
        ids = [r[0] for r in rows]
        try:
            res = self.client.post("/api/v1/readings", {"readings": [r[1] for r in rows]})
        except Exception as e:
            self._handle_error(ids, min(r[2] for r in rows), e)
            return
        self._ok()
        self.outbox.mark(ids, "sent", res)
        self.stats["sent_readings"] += len(ids)

    def _handle_error(self, ids: list[int], attempts: int, e: Exception) -> bool:
        """Restituisce True se si può continuare con le altre righe in questo giro."""
        if isinstance(e, ApiError) and e.status == 422:
            # payload rifiutato (categoria sconosciuta, coordinate, ...): riprovare non serve
            self.outbox.mark(ids, "rejected", error=e.body[:300])
            self.stats["rejected"] += len(ids)
            log.warning("TorinoSegnala: rifiutato (422) %s", e.body[:300])
            return True
        self.outbox.retry_later(ids, attempts, str(e))
        self._fail(e)
        return False

    def _ok(self):
        if self.online is not True:
            log.info("TorinoSegnala: collegato a %s", self.client.base)
        self.online, self.last_error = True, None

    def _fail(self, e: Exception):
        self.stats["errors"] += 1
        msg = str(e)
        if isinstance(e, ApiError) and e.status == 401:
            pause, msg = 300, "401: chiave errata/revocata o POD disattivato dalla Console IT"
        elif isinstance(e, ApiError) and e.status < 500:
            pause = 30
        else:
            pause = 30  # rete assente o errore del server
        if self.online is not False or msg != self.last_error:
            log.warning("TorinoSegnala non raggiungibile (%s), riprovo tra %d s", msg, pause)
        self.online, self.last_error = False, msg
        self._pause_until = time.monotonic() + pause

    # ---------- aiuti ----------
    def _fix(self) -> dict | None:
        try:
            return self.position() if self.position else None
        except Exception:
            log.exception("errore nel leggere la posizione")
            return None

    def _metrics(self) -> dict:
        env = self.rx.env_snapshot() if self.rx else {}
        out = {}
        for k, v in env.items():
            name = ENV_TO_METRIC.get(k)
            if name and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                out[name] = round(float(v), 2)
        return out

    def _photo_b64(self, rel: str) -> str | None:
        import base64
        path = self.root / rel
        try:
            data = path.read_bytes()
        except OSError:
            return None
        return base64.b64encode(data).decode() if len(data) <= MAX_PHOTO_BYTES else None

    def summary(self) -> str:
        state = {None: "mai provato", True: "online", False: "offline"}[self.online]
        return f"{state} {self.stats} coda {self.outbox.counts()}"


def _cli():
    import argparse
    p = argparse.ArgumentParser(description="TorinoSegnala: stato della coda e prova di collegamento")
    p.add_argument("cmd", choices=["status", "ping"])
    p.add_argument("--data", default=os.environ.get("BUSSENSE_DATA") or ("/app/data" if os.path.isdir("/app") else "./data"))
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    up = Uploader(a.data)
    if a.cmd == "status":
        print(f"server {up.client.base}, chiave {'presente' if up.client.key else 'ASSENTE'}")
        print("coda:", up.outbox.counts() or "vuota")
    elif a.cmd == "ping":
        if not up.client.key:
            raise SystemExit("imposta TS_API_KEY")
        res = up.send_heartbeat()
        print("risposta:", res if res is not None else up.last_error)


if __name__ == "__main__":
    _cli()
