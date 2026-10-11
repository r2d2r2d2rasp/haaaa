"""BusSense, App per la UNO Q (lato Linux).

Funziona sia dentro App Lab (con Bridge verso il MCU) sia su un PC per i test:
    BUSSENSE_DATA=./data python main.py
"""
import logging
import os
import time

from bussense.cloud import Uploader
from bussense.gps import Position
from bussense.receiver import Receiver
from bussense.store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("bussense")

DATA = os.environ.get("BUSSENSE_DATA") or ("/app/data" if os.path.isdir("/app") else "./data")
store = Store(DATA, device_id=os.environ.get("BUSSENSE_DEVICE", "unoq-01"))
# BUSSENSE_DEBUG_SAVE_FRAMES=1 -> salva su disco (data/debug_frames/) anche le foto "frame",
# normalmente tenute solo in RAM per privacy. Da usare SOLO per collaudo, mai sul bus.
DEBUG_SAVE_FRAMES = os.environ.get("BUSSENSE_DEBUG_SAVE_FRAMES", "0") == "1"
rx = Receiver(store, port=int(os.environ.get("BUSSENSE_PORT", "8765")), debug_save_frames=DEBUG_SAVE_FRAMES)

# Posizione: telefono, poi modulo GPS facoltativo (BUSSENSE_GPS_DEV o Bridge "gps_fix"), poi TS_FIXED_LAT/LON
position = Position.from_env(rx)
rx.fix_provider = position.current

# Invio a TorinoSegnala (bussense/cloud.py). Senza TS_API_KEY i dati restano in coda in outbox.db.
cloud = None
if os.environ.get("TS_ENABLE", "1") == "1":
    cloud = Uploader(DATA, rx=rx, position=position.current)
    rx.on_report = cloud.on_report

try:
    from arduino.app_utils import App, Bridge  # disponibile solo sulla UNO Q
except ImportError:
    App = Bridge = None

if Bridge:
    # nomi e argomenti devono coincidere con Bridge.notify(...) nello sketch
    Bridge.provide("cabin_co2", lambda co2, t, rh: rx.update_env(co2_ppm=co2, t_c=t, rh_pct=rh))
    Bridge.provide("cabin_voc", lambda sraw, idx: rx.update_env(voc_raw=sraw, voc_idx=idx))
    # modulo GPS sul MCU (facoltativo): Bridge.notify("gps_fix", lat, lon, hdop, speed_mps, heading_deg)
    Bridge.provide("gps_fix", lambda lat, lon, hdop, spd, hdg: position.gps.update(lat, lon, hdop, spd, hdg))

# Visione: brick image_classification con il modello Edge Impulse (bussense/vision.py).
# Se il brick o il modello non ci sono (es. su PC), l'app continua senza visione.
vision = None
if os.environ.get("BUSSENSE_VISION", "1") == "1":
    try:
        from bussense.vision import Vision
        vision = Vision(rx)
        rx.on_frame = vision.submit
    except Exception as e:
        log.warning("visione non attiva: %s", e)

rx.start_in_thread()
if cloud:
    cloud.start_in_thread()
log.info("dati in %s", os.path.abspath(DATA))

_last_log = 0.0


def loop():
    global _last_log
    store.flush_if_due()
    if time.monotonic() - _last_log > 30:
        _last_log = time.monotonic()
        log.info("contatori %s%s", rx.counters, f" visione {vision.stats}" if vision else "")
        if cloud:
            log.info("TorinoSegnala %s", cloud.summary())
    time.sleep(1)


if App:
    App.run(user_loop=loop)
else:
    try:
        while True:
            loop()
    except KeyboardInterrupt:
        if cloud:
            cloud.stop()
        store.close()
