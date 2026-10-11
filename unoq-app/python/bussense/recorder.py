"""Registrazione a pulsante dei sensori del MCU (pulsante su D2, vedi unoq-app/sketch).

È il logger di unoq_registratore/linux_logger portato dentro l'app BusSense: sulla UNO Q gira
una sola App alla volta, quindi senza questo le righe inviate dallo sketch andrebbero perse.
Stesso formato CSV, un file per sessione in data/registrazioni/.
"""
import logging
import threading
import time
from pathlib import Path

log = logging.getLogger("bussense.recorder")

HEADER = "ora_pc,ms,temp_x10,um_x10,co2_ppm,tvoc_ppb,ax_x100,ay_x100,az_x100,gx_x10,gy_x10,gz_x10,luce_0_1023\n"


class Recorder:
    def __init__(self, data_root):
        self.dir = Path(data_root) / "registrazioni"
        self.fh = None
        self.lock = threading.Lock()  # le callback del Bridge arrivano da un altro thread

    def start(self, n):
        with self.lock:
            if self.fh:
                self.fh.close()
            self.dir.mkdir(parents=True, exist_ok=True)
            path = self.dir / (time.strftime("sessione_%Y%m%d_%H%M%S") + f"_n{n}.csv")
            self.fh = open(path, "w", encoding="utf-8")
            self.fh.write(HEADER)
        log.info("sessione avviata: %s", path.name)

    def line(self, line):
        with self.lock:
            if self.fh:
                self.fh.write(time.strftime("%H:%M:%S,") + str(line) + "\n")
                self.fh.flush()

    def stop(self, n):
        with self.lock:
            if self.fh:
                self.fh.close()
                self.fh = None
        log.info("sessione chiusa, campioni: %s", n)
