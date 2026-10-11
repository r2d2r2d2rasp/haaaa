"""Riconoscimento sulle foto "frame" inviate dal telefono.

Usa il brick App Lab `arduino:image_classification` con un modello Edge Impulse
addestrato sulle classi di LABEL_TO_TYPE (+ "normale"). La classificazione dice
"in questa foto c'è una buca / spazzatura", senza riquadro: per la segnalazione
basta, perché la posizione la dà il GPS.

- Gira in un thread separato: il server WebSocket non si blocca mai.
- Coda da 1 foto: se l'inferenza è più lenta dell'arrivo, si tiene solo l'ultima.
- Conferma temporale: si segnala solo se la stessa classe compare in almeno
  CONFIRM_K delle ultime CONFIRM_N foto (filtra i falsi positivi isolati).
- Deduplica: stessa classe entro DEDUP_M metri e DEDUP_S secondi = stessa segnalazione.
"""
import logging
import os
import queue
import threading
import time
from collections import deque

from .receiver import haversine_m

log = logging.getLogger("bussense.vision")

# etichetta del modello Edge Impulse -> tipo di evento (PIANO.md 5.1)
LABEL_TO_TYPE = {
    "buca": "pothole",
    "cassonetto_pieno": "overflowing_bin",
    "rifiuti": "bulky_waste",
}
MIN_CONF = float(os.environ.get("BUSSENSE_VISION_CONF", "0.70"))
CONFIRM_N, CONFIRM_K = 3, 2
DEDUP_M, DEDUP_S = 20.0, 60.0
MODEL_NAME = os.environ.get("BUSSENSE_VISION_MODEL", "ei-urban-cls-v1")


class Vision:
    def __init__(self, rx):
        self.rx = rx
        self.q: queue.Queue = queue.Queue(maxsize=1)
        self.history: deque = deque(maxlen=CONFIRM_N)      # (label|None, conf, meta)
        self.last_report: dict[str, tuple] = {}            # type -> (t, lat, lon)
        self.stats = {"frames": 0, "dropped": 0, "reports": 0, "ms_avg": 0.0}
        from arduino.app_bricks.image_classification import ImageClassification  # solo sulla UNO Q
        self.model = ImageClassification(confidence=0.0)
        threading.Thread(target=self._worker, name="vision", daemon=True).start()
        log.info("visione attiva: classi %s, soglia %.2f", list(LABEL_TO_TYPE), MIN_CONF)

    def submit(self, jpeg: bytes, meta: dict):
        """Callback per rx.on_frame (chiamata dal thread di rete: non deve bloccare)."""
        try:
            self.q.put_nowait((jpeg, meta))
        except queue.Full:
            try:
                self.q.get_nowait()          # scarta la foto vecchia, tiene la nuova
                self.stats["dropped"] += 1
            except queue.Empty:
                pass
            self.q.put_nowait((jpeg, meta))

    def _worker(self):
        while True:
            jpeg, meta = self.q.get()
            t0 = time.monotonic()
            try:
                out = self.model.classify(jpeg)
            except Exception:
                log.exception("errore di inferenza")
                continue
            ms = (time.monotonic() - t0) * 1000
            n = self.stats["frames"] = self.stats["frames"] + 1
            self.stats["ms_avg"] += (ms - self.stats["ms_avg"]) / n
            label, conf = self._top(out)
            log.debug("foto seq=%s -> %s %.2f (%.0f ms)", meta.get("seq"), label, conf, ms)
            self.history.append((label if conf >= MIN_CONF else None, conf, meta))
            self._maybe_report(label, conf, meta)

    @staticmethod
    def _top(out) -> tuple[str | None, float]:
        if not out or not out.get("classification"):
            return None, 0.0
        best = max(out["classification"], key=lambda c: float(c["confidence"]))
        return best["class_name"], float(best["confidence"]) / 100.0   # il brick dà percentuali

    def _maybe_report(self, label, conf, meta):
        typ = LABEL_TO_TYPE.get(label or "")
        if typ is None or conf < MIN_CONF:
            return
        hits = [h for h in self.history if h[0] == label]
        if len(hits) < CONFIRM_K:
            return
        lat, lon = meta.get("lat"), meta.get("lon")
        if lat is None:
            return                                   # senza posizione non ha senso segnalare
        prev = self.last_report.get(typ)
        now = time.time()
        if prev and now - prev[0] < DEDUP_S and haversine_m(prev[1], prev[2], lat, lon) < DEDUP_M:
            return
        best = max(hits, key=lambda h: h[1])         # la foto più sicura tra quelle concordi
        bm = best[2]
        self.last_report[typ] = (now, lat, lon)
        self.stats["reports"] += 1
        self.rx.report(
            type=typ, src="vision", conf=best[1], ts_ms=bm["ts_ms"], ts_src=bm.get("ts_src"),
            model=MODEL_NAME, phone_id=bm.get("device"),
            detail={"label": label, "votes": f"{len(hits)}/{len(self.history)}", "frame_seq": bm.get("seq")},
            **{k: bm.get(k) for k in ("lat", "lon", "acc_m", "speed_mps", "heading_deg", "fix_age_ms")},
        )
        # nessuna immagine salvata: privacy.redact non è ancora implementata (fail-closed)
