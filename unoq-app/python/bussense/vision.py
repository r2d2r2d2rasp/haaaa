"""Riconoscimento sulle foto "frame" inviate dal telefono.

Un classificatore addestrato sulle classi di LABEL_TO_TYPE (+ "normale"). La
classificazione dice "in questa foto c'è una buca / spazzatura", senza riquadro:
per la segnalazione basta, perché la posizione la dà il GPS.

Due motori, scelti all'avvio:
- LiteRT (bussense/classifier.py) se esiste il modello BUSSENSE_TFLITE, di default
  python/models/bussense_int8.tflite, prodotto da ml/export_tflite.py --app;
- altrimenti il brick App Lab `arduino:image_classification` (modello Edge Impulse).

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
from pathlib import Path

from .receiver import haversine_m

log = logging.getLogger("bussense.vision")

# etichetta del modello -> tipo di evento (PIANO.md 5.1); le altre ("normale") non si segnalano
LABEL_TO_TYPE = {
    "buca": "pothole",
    "cassonetto_pieno": "overflowing_bin",
    "rifiuti": "bulky_waste",
}
MIN_CONF = float(os.environ.get("BUSSENSE_VISION_CONF", "0.70"))
CONFIRM_N, CONFIRM_K = 3, 2
DEDUP_M, DEDUP_S = 20.0, 60.0
TFLITE = Path(os.environ.get("BUSSENSE_TFLITE")
              or Path(__file__).resolve().parent.parent / "models" / "bussense_int8.tflite")


def _load_backend() -> tuple[str, "callable"]:
    """-> (nome del modello per la piattaforma, funzione jpeg -> (label, conf 0..1))."""
    path = TFLITE
    if path.is_file():
        from .classifier import Classifier  # numpy, Pillow, ai-edge-litert: servono solo qui
        clf = Classifier(path, threads=int(os.environ.get("BUSSENSE_VISION_THREADS", "4")))
        log.info("visione LiteRT: %s, classi %s", path.name, clf.labels)
        return os.environ.get("BUSSENSE_VISION_MODEL", path.stem), clf.top
    from arduino.app_bricks.image_classification import ImageClassification  # solo sulla UNO Q
    model = ImageClassification(confidence=0.0)
    log.info("visione Edge Impulse (brick): %s non trovato", path)
    return os.environ.get("BUSSENSE_VISION_MODEL", "ei-urban-cls-v1"), lambda jpeg: _top_ei(model.classify(jpeg))


def _top_ei(out) -> tuple[str | None, float]:
    if not out or not out.get("classification"):
        return None, 0.0
    best = max(out["classification"], key=lambda c: float(c["confidence"]))
    return best["class_name"], float(best["confidence"]) / 100.0   # il brick dà percentuali


class Vision:
    def __init__(self, rx):
        self.rx = rx
        self.q: queue.Queue = queue.Queue(maxsize=1)
        self.history: deque = deque(maxlen=CONFIRM_N)      # (label|None, conf, meta)
        self.last_report: dict[str, tuple] = {}            # type -> (t, lat, lon)
        self.stats = {"frames": 0, "dropped": 0, "reports": 0, "ms_avg": 0.0}
        self.model_name, self._classify = _load_backend()
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
                label, conf = self._classify(jpeg)
            except Exception:
                log.exception("errore di inferenza")
                continue
            ms = (time.monotonic() - t0) * 1000
            n = self.stats["frames"] = self.stats["frames"] + 1
            self.stats["ms_avg"] += (ms - self.stats["ms_avg"]) / n
            log.debug("foto seq=%s -> %s %.2f (%.0f ms)", meta.get("seq"), label, conf, ms)
            self.history.append((label if conf >= MIN_CONF else None, conf, meta))
            self._maybe_report(label, conf, meta)

    def _maybe_report(self, label, conf, meta):
        typ = LABEL_TO_TYPE.get(label or "")
        if typ is None or conf < MIN_CONF:
            return
        hits = [h for h in self.history if h[0] == label]
        if len(hits) < CONFIRM_K:
            return
        best = max(hits, key=lambda h: h[1])         # la foto più sicura tra quelle concordi
        bm = best[2]
        pos = {k: bm.get(k) for k in ("lat", "lon", "acc_m", "speed_mps", "heading_deg", "fix_age_ms")}
        pos_src = "phone"
        if pos["lat"] is None and self.rx.fix_provider:
            # foto senza fix (al chiuso, GPS appena acceso): gps.py prova l'ultimo fix del telefono,
            # il modulo GPS, poi la posizione fissa TS_FIXED_LAT/LON
            fix = self.rx.fix_provider()
            if fix and fix.get("lat") is not None:
                pos.update({k: fix.get(k) for k in ("lat", "lon", "acc_m", "speed_mps", "heading_deg")})
                pos_src = fix.get("src", "fallback")
        lat, lon = pos["lat"], pos["lon"]
        if lat is None:
            return                                   # senza posizione non ha senso segnalare
        prev = self.last_report.get(typ)
        now = time.time()
        if prev and now - prev[0] < DEDUP_S and haversine_m(prev[1], prev[2], lat, lon) < DEDUP_M:
            return
        self.last_report[typ] = (now, lat, lon)
        self.stats["reports"] += 1
        self.rx.report(
            type=typ, src="vision", conf=best[1], ts_ms=bm["ts_ms"], ts_src=bm.get("ts_src"),
            model=self.model_name, phone_id=bm.get("device"),
            detail={"label": label, "votes": f"{len(hits)}/{len(self.history)}", "frame_seq": bm.get("seq"),
                    "pos_src": pos_src},
            **pos,
        )
        # nessuna immagine salvata: privacy.redact non è ancora implementata (fail-closed)
