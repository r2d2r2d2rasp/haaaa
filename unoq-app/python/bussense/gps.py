"""Posizione corrente della UNO Q, da più fonti in ordine di priorità.

1. telefono   - l'ultimo messaggio "track" ricevuto (rx.last_fix), se recente
2. modulo GPS - facoltativo, in uno di due modi:
     a) collegato al lato Linux (USB o UART): BUSSENSE_GPS_DEV=/dev/ttyUSB0 (BUSSENSE_GPS_BAUD, default 9600),
        legge le frasi NMEA $..RMC / $..GGA;
     b) collegato al MCU: lo sketch chiama Bridge.notify("gps_fix", lat, lon, hdop, speed_mps, heading_deg)
        e main.py lo passa a GpsModule.update(...)
3. posizione fissa - TS_FIXED_LAT / TS_FIXED_LON (POD fermo o prove al banco)

Il modulo GPS è del tutto facoltativo: se il dispositivo non c'è o non dà fix, si usa solo il telefono.
"""
import logging
import os
import threading
import time

log = logging.getLogger("bussense.gps")

FRESH_S = 10.0  # oltre questa età un fix non vale più come posizione "corrente"


class GpsModule:
    """Ultimo fix del modulo GPS (da NMEA seriale o da Bridge)."""

    def __init__(self):
        self.fix: dict | None = None
        self._mono = 0.0
        self.sentences = 0
        self.bad = 0

    def update(self, lat, lon, hdop=None, speed_mps=None, heading_deg=None):
        if lat is None or lon is None or (lat == 0 and lon == 0):
            return
        self.fix = {"lat": float(lat), "lon": float(lon),
                    "acc_m": None if hdop is None else round(float(hdop) * 5.0, 1),  # stima grezza da HDOP
                    "speed_mps": speed_mps, "heading_deg": heading_deg, "src": "gps_module"}
        self._mono = time.monotonic()

    def current(self) -> dict | None:
        return self.fix if self.fix and time.monotonic() - self._mono < FRESH_S else None

    # ---------- NMEA ----------
    def feed_nmea(self, line: str):
        line = line.strip()
        if not line.startswith("$") or "*" not in line:
            return
        body, _, cks = line[1:].partition("*")
        x = 0
        for ch in body:
            x ^= ord(ch)
        if cks[:2].upper() != f"{x:02X}":
            self.bad += 1
            return
        f = body.split(",")
        kind = f[0][2:]
        self.sentences += 1
        try:
            if kind == "RMC" and len(f) > 8 and f[2] == "A":           # A = fix valido
                speed = float(f[7]) * 0.514444 if f[7] else None      # nodi -> m/s
                heading = float(f[8]) if f[8] else None
                prev = self.fix or {}
                self.update(_deg(f[3], f[4]), _deg(f[5], f[6]), _hdop_of(prev), speed, heading)
            elif kind == "GGA" and len(f) > 8 and f[6] not in ("", "0"):  # 0 = nessun fix
                prev = self.fix or {}
                self.update(_deg(f[2], f[3]), _deg(f[4], f[5]), float(f[8]) if f[8] else None,
                            prev.get("speed_mps"), prev.get("heading_deg"))
        except (ValueError, IndexError):
            self.bad += 1

    def start_serial(self, dev: str, baud: int = 9600):
        threading.Thread(target=self._serial_loop, args=(dev, baud), name="gps", daemon=True).start()

    def _serial_loop(self, dev: str, baud: int):
        warned = False
        while True:
            try:
                with open(dev, "rb", buffering=0) as f:
                    _set_baud(f.fileno(), baud)
                    log.info("modulo GPS su %s a %d baud", dev, baud)
                    warned = False
                    buf = b""
                    while True:
                        chunk = f.read(256)
                        if not chunk:
                            time.sleep(0.1)
                            continue
                        buf += chunk
                        while b"\n" in buf:
                            raw, buf = buf.split(b"\n", 1)
                            self.feed_nmea(raw.decode("ascii", "ignore"))
                        buf = buf[-512:]
            except OSError as e:
                if not warned:
                    log.warning("modulo GPS %s non disponibile (%s), riprovo ogni 10 s", dev, e)
                    warned = True
                time.sleep(10)


def _deg(value: str, hemi: str) -> float | None:
    """ddmm.mmmm + N/S/E/W -> gradi decimali."""
    if not value:
        return None
    dot = value.index(".") if "." in value else len(value)
    deg = float(value[:dot - 2]) + float(value[dot - 2:]) / 60.0
    return -deg if hemi in ("S", "W") else deg


def _hdop_of(fix: dict):
    return None if fix.get("acc_m") is None else fix["acc_m"] / 5.0


def _set_baud(fd: int, baud: int):
    try:
        import termios  # solo Linux
    except ImportError:
        return
    speed = getattr(termios, f"B{baud}", None)
    if speed is None:
        return
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0                                  # iflag
    attrs[1] = 0                                  # oflag
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0                                  # lflag: modo raw
    attrs[4] = attrs[5] = speed
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


class Position:
    """position.current() -> dict con lat/lon/acc_m/speed_mps/heading_deg/src, oppure None."""

    def __init__(self, rx=None, gps: GpsModule | None = None, fixed: tuple[float, float] | None = None):
        self.rx, self.gps, self.fixed = rx, gps, fixed

    @classmethod
    def from_env(cls, rx=None) -> "Position":
        gps = GpsModule()
        dev = os.environ.get("BUSSENSE_GPS_DEV")
        if dev:
            gps.start_serial(dev, int(os.environ.get("BUSSENSE_GPS_BAUD", "9600")))
        fixed = None
        if os.environ.get("TS_FIXED_LAT") and os.environ.get("TS_FIXED_LON"):
            fixed = (float(os.environ["TS_FIXED_LAT"]), float(os.environ["TS_FIXED_LON"]))
        return cls(rx, gps, fixed)

    def current(self) -> dict | None:
        rx = self.rx
        if rx and rx.last_fix and rx.last_fix.get("lat") is not None and time.monotonic() - rx.last_fix_mono < FRESH_S:
            f = rx.last_fix
            return {**{k: f.get(k) for k in ("lat", "lon", "acc_m", "speed_mps", "heading_deg")}, "src": "phone"}
        if self.gps and (g := self.gps.current()):
            return dict(g)
        if self.fixed:
            return {"lat": self.fixed[0], "lon": self.fixed[1], "acc_m": None, "speed_mps": 0.0,
                    "heading_deg": None, "src": "fixed"}
        return None
