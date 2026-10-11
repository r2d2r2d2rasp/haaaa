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
from bussense.recorder import Recorder
from bussense.store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("bussense")

DATA = os.environ.get("BUSSENSE_DATA") or ("/app/data" if os.path.isdir("/app") else "./data")

# App Lab non passa variabili d'ambiente all'app: la configurazione (TS_API_KEY, TS_FIXED_LAT, ...)
# si scrive in data/bussense.env, una riga KEY=valore. data/ è fuori dal repo, quindi la chiave
# non finisce su git. Le variabili già presenti nell'ambiente hanno la precedenza.
_cfg = os.path.join(DATA, "bussense.env")
if os.path.isfile(_cfg):
    with open(_cfg, encoding="utf-8") as f:
        for line in f:
            k, sep, v = line.strip().partition("=")
            if sep and k and not k.startswith("#"):
                os.environ.setdefault(k.strip(), v.strip().strip('"'))
    log.info("configurazione da %s", _cfg)

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

recorder = Recorder(DATA)

if Bridge:
    # nomi e argomenti devono coincidere con Bridge.notify(...) nello sketch (unoq-app/sketch)
    # SGP30: la CO2 è "equivalente", stimata dai gas e non misurata come farebbe un SCD41
    Bridge.provide("cabin_co2", lambda co2, t, rh: rx.update_env(co2_ppm=co2, t_c=t, rh_pct=rh))
    Bridge.provide("cabin_voc", lambda sraw, idx: rx.update_env(voc_raw=sraw, voc_idx=idx))
    Bridge.provide("cabin_extra", lambda tvoc, light: rx.update_env(tvoc_ppb=tvoc, light_pct=light))
    # registrazione a pulsante (D2) in CSV, come unoq_registratore/linux_logger
    Bridge.provide("log_start", recorder.start)
    Bridge.provide("log_line", recorder.line)
    Bridge.provide("log_stop", recorder.stop)
    # modulo GPS sul MCU (facoltativo): Bridge.notify("gps_fix", lat, lon, hdop, speed_mps, heading_deg)
    Bridge.provide("gps_fix", lambda lat, lon, hdop, spd, hdg: position.gps.update(lat, lon, hdop, spd, hdg))

# Visione (bussense/vision.py): modello LiteRT in python/models/ se c'è, altrimenti il brick
# image_classification di Edge Impulse. Se nessuno dei due è disponibile, l'app continua senza visione.
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
_last_status = 0.0


def push_status():
    """Stato per la pagina BUSSENSE dell'OLED: telefono, segnalazioni, collegamento a TorinoSegnala."""
    phone = time.monotonic() - rx.last_fix_mono < 10                # i track arrivano a 1 Hz
    reports = rx.counters["event"] + (vision.stats["reports"] if vision else 0)
    sent = cloud.stats["sent_reports"] if cloud else 0
    # 0 = invio spento o senza chiave, 1 = ultimo invio riuscito, 2 = errore (rete o chiave)
    net = 0 if not cloud or not cloud.client.key else (1 if cloud.online else 2 if cloud.online is False else 0)
    try:
        Bridge.notify("bs_status", bool(phone), int(reports), int(sent), int(net))
    except Exception:
        log.debug("bs_status non inviato", exc_info=True)


def loop():
    global _last_log, _last_status
    store.flush_if_due()
    if Bridge and time.monotonic() - _last_status > 2:
        _last_status = time.monotonic()
        push_status()
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
