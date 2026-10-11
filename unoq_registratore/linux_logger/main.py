# Lato Linux della UNO Q (App Lab): riceve le righe dallo sketch e le salva sull'eMMC interna.
# Un file CSV per sessione in /home/arduino/registrazioni/
import os
import time
from arduino.app_utils import App, Bridge

DIR = "/home/arduino/registrazioni"
HEADER = "ora_pc,ms,temp_x10,um_x10,co2_ppm,tvoc_ppb,ax_x100,ay_x100,az_x100,gx_x10,gy_x10,gz_x10,luce_0_1023\n"
fh = None


def log_start(n):
    global fh
    os.makedirs(DIR, exist_ok=True)
    if fh:
        fh.close()
    name = time.strftime("sessione_%Y%m%d_%H%M%S") + f"_n{n}.csv"
    fh = open(os.path.join(DIR, name), "w")
    fh.write(HEADER)
    print("Sessione avviata:", name)


def log_line(line):
    if fh:
        fh.write(time.strftime("%H:%M:%S,") + line + "\n")
        fh.flush()


def log_stop(n):
    global fh
    if fh:
        fh.close()
        fh = None
    print("Sessione chiusa, campioni:", n)


Bridge.provide("log_start", log_start)
Bridge.provide("log_line", log_line)
Bridge.provide("log_stop", log_stop)

App.run()
