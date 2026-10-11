"""Genera le grafiche del modello di visione per la presentazione.

Ogni grafica e un SVG 1600x900 (16:9, la misura di una slide). I colori sono scritti come
var(--token, #valore): dentro la pagina web seguono il tema chiaro/scuro, nei file per le
slide (cartella svg/) il var() viene sostituito dal valore chiaro, cosi PowerPoint, Keynote
e Google Slides li leggono senza problemi. I PNG si ricavano dagli SVG con rsvg-convert.

Tutti i numeri vengono da docs/MODELLO.md (misure reali del modello v2).

    python genera.py                 # scrive sorgenti/, svg/
    rsvg-convert -z 2 svg/X.svg > png/X.png   # (lo fa crea_png.sh)
"""
import re
from pathlib import Path

QUI = Path(__file__).resolve().parent
W, H = 1600, 900

CHIARO = {
    "paper": "#f7f6f2", "panel": "#ffffff", "panel2": "#eeede7", "ink": "#1e2227", "ink2": "#4b5058",
    "muted": "#7a7f87", "line": "#d4d2ca", "accent": "#e3a008", "accent-soft": "#f7e7bd",
    "buca": "#2a78d6", "rif": "#1baf7a", "cass": "#eb6834", "norm": "#7d828a", "on-color": "#ffffff",
    "s100": "#cde2fb", "s200": "#9ec5f4", "s300": "#6da7ec", "s400": "#3987e5", "s500": "#256abf", "s650": "#104281",
}
SCURO = {
    "paper": "#16181b", "panel": "#1f2226", "panel2": "#282b30", "ink": "#f1f0ea", "ink2": "#c3c2b7",
    "muted": "#8d9198", "line": "#3a3d43", "accent": "#f0b429", "accent-soft": "#4a3d16",
    "buca": "#3987e5", "rif": "#199e70", "cass": "#d95926", "norm": "#8d9198", "on-color": "#ffffff",
    "s100": "#22324a", "s200": "#1c4475", "s300": "#1c5cab", "s400": "#2a78d6", "s500": "#5598e7", "s650": "#9ec5f4",
}
CLASSE = {"buca": "buca", "rifiuti": "rif", "cassonetto": "cass", "normale": "norm"}

DISP = "'IBM Plex Sans Condensed','Arial Narrow',sans-serif"
BODY = "'IBM Plex Sans','Segoe UI',Arial,sans-serif"
MONO = "'IBM Plex Mono',Consolas,monospace"


def c(tok: str) -> str:
    return f"var(--{tok}, {CHIARO[tok]})"


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def t(x, y, s, size=18, fill="ink", weight=400, family=BODY, anchor="start", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{c(fill)}" text-anchor="{anchor}" {extra}>{esc(s)}</text>')


def r(x, y, w, h, fill="panel", stroke=None, rx=10, sw=1.5, extra=""):
    st = f' stroke="{c(stroke)}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{c(fill)}"{st} {extra}/>'


def rt(x, y, w, h, fill, titolo, opacita=1.0):
    """Rettangolo-dato con tooltip al passaggio del mouse (nella pagina web)."""
    op = f' opacity="{opacita}"' if opacita < 1 else ""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" fill="{c(fill)}"{op}>'
            f'<title>{esc(titolo)}</title></rect>')


def freccia(x1, y1, x2, y2, col="ink2", w=2.5, testa=11):
    import math
    a = math.atan2(y2 - y1, x2 - x1)
    bx, by = x2 - testa * math.cos(a), y2 - testa * math.sin(a)
    p1 = (bx + testa * 0.55 * math.sin(a), by - testa * 0.55 * math.cos(a))
    p2 = (bx - testa * 0.55 * math.sin(a), by + testa * 0.55 * math.cos(a))
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="{c(col)}" stroke-width="{w}"/>'
            f'<polygon points="{x2:.1f},{y2:.1f} {p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}" fill="{c(col)}"/>')


def testata(titolo, sotto):
    return t(64, 86, titolo, 46, "ink", 700, DISP) + t(64, 126, sotto, 22, "ink2")


def svg(nome, corpo, descr):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'role="img" aria-labelledby="t-{nome}"><title id="t-{nome}">{esc(descr)}</title>'
            f'{r(0, 0, W, H, "paper", rx=0)}{corpo}</svg>')


def righe(x, y, testi, size=16, fill="ink2", passo=22, **kw):
    return "".join(t(x, y + i * passo, s, size, fill, **kw) for i, s in enumerate(testi))


# ---------------------------------------------------------------------------- 01 sistema
def g_sistema():
    o = [testata("Come funziona BusSense",
                 "La foto viene analizzata sulla UNO Q: alla piattaforma arriva solo l'esito")]
    # telefono
    o.append(r(64, 200, 290, 470, "panel", "line", 14))
    o.append(t(88, 236, "TELEFONO", 15, "muted", 600, MONO, extra='letter-spacing="2"'))
    o.append(t(88, 268, "Galaxy A26", 28, "ink", 700, DISP))
    items = [("Fotocamera", ["1 foto ogni ~4 m percorsi", "1 al secondo in modalità demo"]),
             ("GPS", ["1 Hz, precisione 5–15 m"]), ("Nitidezza", ["scarta le foto mosse"])]
    y = 318
    for nome, det in items:
        o.append(t(88, y, nome, 19, "ink", 600))
        o.append(righe(88, y + 26, det, 16))
        y += 40 + 26 * len(det) + 14
    o.append(r(88, 590, 242, 52, "panel2", rx=8))
    o.append(t(209, 622, "fa da hotspot Wi-Fi", 16, "ink2", anchor="middle"))

    # UNO Q
    o.append(r(450, 170, 760, 620, "panel", "ink", 16, 2))
    o.append(t(476, 206, "ARDUINO UNO Q", 15, "muted", 600, MONO, extra='letter-spacing="2"'))
    o.append(t(476, 238, "Dentro il POD, sul bus", 28, "ink", 700, DISP))
    o.append(r(476, 262, 708, 262, "panel2", rx=12))
    o.append(t(496, 292, "Linux · Qualcomm QRB2210 · 4 core Cortex-A53", 16, "ink2", 600))
    passi = [("receiver.py", "Riceve", ["foto solo in RAM", "mai su disco"], "panel"),
             ("classifier.py", "Riconosce", ["MobileNetV2 int8", "41 ms per foto"], "accent-soft"),
             ("vision.py", "Decide", ["soglia 0,70", "2 foto su 3", "no doppioni 20 m"], "panel"),
             ("cloud.py", "Invia", ["coda su disco", "riprova senza rete"], "panel")]
    bw, gap, x0 = 156, 18, 496
    for i, (file, verbo, det, fill) in enumerate(passi):
        x = x0 + i * (bw + gap)
        o.append(r(x, 312, bw, 190, fill, "accent" if fill == "accent-soft" else "line", 10,
                   2.5 if fill == "accent-soft" else 1.5))
        o.append(t(x + 14, 344, verbo, 24, "ink", 700, DISP))
        o.append(t(x + 14, 368, file, 14, "muted", 500, MONO))
        o.append(righe(x + 14, 404, det, 15, "ink2", 22))
        if i < 3:
            o.append(freccia(x + bw + 2, 407, x + bw + gap - 1, 407, "ink2", 2.2, 9))
    # MCU
    o.append(r(476, 584, 708, 180, "panel2", rx=12))
    o.append(t(496, 614, "Microcontrollore STM32U585 · sensori e display", 16, "ink2", 600))
    chips = ["AHT20 · temp. e umidità", "SGP30 · CO2eq, TVOC", "Luce · A0",
             "IMU · accelerazioni", "OLED · stato", "Pulsante · registra"]
    for i, s in enumerate(chips):
        x = 496 + (i % 3) * 228
        y = 634 + (i // 3) * 56
        o.append(r(x, y, 216, 44, "panel", "line", 8))
        o.append(t(x + 14, y + 28, s, 15, "ink", 500))
    # Bridge: MCU -> cloud
    o.append(freccia(1110, 584, 1110, 504, "ink2", 2.2, 9))
    o.append(t(1098, 560, "Bridge: misure", 14, "ink2", 500, anchor="end"))

    # piattaforma
    o.append(r(1300, 200, 236, 470, "panel", "line", 14))
    o.append(t(1322, 236, "PIATTAFORMA", 15, "muted", 600, MONO, extra='letter-spacing="2"'))
    o.append(t(1322, 268, "TorinoSegnala", 28, "ink", 700, DISP))
    y = 318
    for nome, det in [("Segnalazioni", ["buca, rifiuti, cassonetto", "+ posizione + sensori"]),
                      ("Misure dei sensori", ["ogni 60 secondi"]), ("Mappa", ["pubblica e area Comune"])]:
        o.append(t(1322, y, nome, 19, "ink", 600))
        o.append(righe(1322, y + 26, det, 15))
        y += 40 + 26 * len(det) + 14

    # frecce di rete
    o.append(freccia(354, 407, 494, 407, "ink", 3, 13))
    o.append(t(402, 392, "Wi-Fi", 15, "ink", 600, anchor="middle"))
    o.append(t(402, 432, "foto + GPS", 14, "ink2", anchor="middle"))
    o.append(freccia(1184, 407, 1298, 407, "ink", 3, 13))
    o.append(t(1255, 392, "HTTPS", 15, "ink", 600, anchor="middle"))
    o.append(t(1255, 432, "chiave API", 14, "ink2", anchor="middle"))

    o.append(r(64, 812, 1472, 56, "accent-soft", rx=10))
    o.append(t(88, 847, "Le foto non lasciano mai la board. Alla piattaforma arrivano solo categoria, "
                        "confidenza, posizione e misure dei sensori.", 19, "ink", 500))
    return svg("sistema", "".join(o), "Schema del sistema BusSense: telefono, UNO Q, piattaforma")


# ---------------------------------------------------------------------------- 02 rete neurale
def blocco3d(x, ybase, w, h, fill, d=12, stroke="ink2"):
    """Mappa di caratteristiche come parallelepipedo: altezza = risoluzione, larghezza = canali."""
    y = ybase - h / 2
    top = f"{x},{y} {x + d},{y - d} {x + w + d},{y - d} {x + w},{y}"
    side = f"{x + w},{y} {x + w + d},{y - d} {x + w + d},{y + h - d} {x + w},{y + h}"
    return (f'<polygon points="{top}" fill="{c(fill)}" stroke="{c(stroke)}" stroke-width="1" opacity="0.75"/>'
            f'<polygon points="{side}" fill="{c(fill)}" stroke="{c(stroke)}" stroke-width="1" opacity="0.55"/>'
            + r(x, y, w, h, fill, stroke, 2, 1))


def g_rete():
    import math
    o = [testata("La rete neurale",
                 "MobileNetV2 pre-addestrata su ImageNet + una testa nuova a 4 classi")]
    yc = 440
    hres = lambda res: 52 + 205 * math.sqrt(res / 224)
    wch = lambda ch: 10 + 9 * math.log2(ch / 8)

    # immagine d'ingresso: asfalto con una buca
    x = 64
    o.append('<defs><radialGradient id="g-buca" cx="50%" cy="55%" r="50%">'
             f'<stop offset="0" stop-color="#2b2a28"/><stop offset="1" stop-color="#6a6862"/></radialGradient></defs>')
    o.append(f'<rect x="{x}" y="{yc - 95}" width="190" height="190" rx="6" fill="#8d8a83"/>')
    o.append(f'<ellipse cx="{x + 98}" cy="{yc + 8}" rx="54" ry="34" fill="url(#g-buca)"/>')
    o.append(f'<path d="M{x + 10} {yc - 60} q60 -22 170 6" stroke="#e3a008" stroke-width="7" fill="none"/>')
    o.append(t(x + 95, yc + 125, "foto 224×224", 16, "ink", 600, anchor="middle"))
    o.append(t(x + 95, yc + 147, "pixel 0–255", 14, "muted", 400, MONO, anchor="middle"))
    x += 190 + 22
    o.append(freccia(x - 18, yc, x + 4, yc, "ink2", 2, 8))
    o.append(r(x + 6, yc - 70, 34, 140, "panel2", "line", 6))
    o.append(t(x + 23, yc + 4, "÷127,5 − 1", 13, "ink2", 500, MONO, anchor="middle",
               extra=f'transform="rotate(-90 {x + 23} {yc})"'))
    o.append(t(x + 23, yc + 96, "scala", 13, "muted", anchor="middle"))
    x += 40 + 26

    blocchi = [("stem", 112, 32, None)] + [(f"×{n}", res, ch, n) for res, ch, n in
                                           [(112, 16, 1), (56, 24, 2), (28, 32, 3), (14, 64, 4),
                                            (14, 96, 3), (7, 160, 3), (7, 320, 1)]] + [("1×1", 7, 1280, None)]
    gap = 26
    pos = []
    for i, (lab, res, ch, n) in enumerate(blocchi):
        if i:
            o.append(freccia(x - gap + 4, yc, x - 3, yc, "ink2", 1.8, 7))
        w, h = wch(ch), hres(res)
        ft = i >= 5  # dal blocco con 96 canali (contiene block_12) in poi: fine-tuning
        o.append(blocco3d(x, yc, w, h, "accent-soft" if ft else "panel2", stroke="accent" if ft else "ink2"))
        o.append(t(x + w / 2 + 6, yc + h / 2 + 30, f"{res}²", 14, "ink", 600, MONO, anchor="middle"))
        o.append(t(x + w / 2 + 6, yc + h / 2 + 50, ch, 14, "ink2", 400, MONO, anchor="middle"))
        o.append(t(x + w / 2 + 6, yc - h / 2 - 22, lab, 14, "muted", 500, MONO, anchor="middle"))
        pos.append((x, w, h))
        x += w + 12 + gap
    xb0, xb1 = pos[0][0], pos[-1][0] + pos[-1][1] + 12
    xf0 = pos[5][0]
    # parentesi sopra
    yb = yc - hres(112) / 2 - 64
    o.append(f'<path d="M{xb0} {yb + 10} v-10 h{xb1 - xb0} v10" stroke="{c("ink2")}" stroke-width="2" fill="none"/>')
    o.append(t(xb0, yb - 14, "MobileNetV2 · 17 blocchi inverted residual · 154 strati · 2,26 M parametri", 17, "ink", 600))
    yf = yc - hres(14) / 2 - 44
    o.append(f'<path d="M{xf0} {yf + 9} v-9 h{xb1 - xf0} v9" stroke="{c("accent")}" stroke-width="3" fill="none"/>')
    o.append(t(xf0, yf - 10, "fine-tuning: ultimi 40 strati", 15, "ink", 600))
    # legenda assi
    o.append(t(xb0, yc + hres(112) / 2 + 92, "altezza = risoluzione (224 → 7)   ·   "
                                             "larghezza = canali (32 → 1280)   ·   sotto: lato² e canali", 14, "muted"))

    # testa
    x = xb1 + 14
    o.append(freccia(x, yc, x + 22, yc, "ink2", 2, 8))
    x += 28
    o.append(r(x, yc - 80, 18, 160, "accent-soft", "accent", 3, 2))
    o.append(t(x + 9, yc + 106, "media", 14, "ink", 600, anchor="middle"))
    o.append(t(x + 9, yc + 126, "1280", 14, "ink2", 400, MONO, anchor="middle"))
    x += 18
    o.append(freccia(x + 4, yc, x + 28, yc, "ink2", 2, 8))
    x += 34
    o.append(r(x, yc - 48, 70, 96, "accent-soft", "accent", 8, 2))
    o.append(t(x + 35, yc - 8, "Dense", 16, "ink", 700, anchor="middle"))
    o.append(t(x + 35, yc + 14, "4", 16, "ink", 700, MONO, anchor="middle"))
    o.append(t(x + 35, yc + 34, "softmax", 13, "ink2", anchor="middle"))
    o.append(t(x + 35, yc + 106, "testa nuova", 14, "ink", 600, anchor="middle"))
    o.append(t(x + 35, yc + 126, "5.124 par.", 14, "ink2", 400, MONO, anchor="middle"))
    x += 70
    # uscite reali (foto buca_00004 della validation)
    usc = [("buca", 0.980, "buca"), ("rifiuti", 0.008, "rif"), ("normale", 0.008, "norm"), ("cassonetto", 0.004, "cass")]
    bx, maxw = x + 44, 1536 - (x + 44) - 4
    for i, (nome, p, tok) in enumerate(usc):
        y = yc - 92 + i * 50
        o.append(f'<line x1="{x + 4}" y1="{yc}" x2="{bx - 4}" y2="{y + 14}" stroke="{c("line")}" stroke-width="1.5"/>')
        ww = max(4, maxw * p * 0.62)
        o.append(rt(bx, y, ww, 28, tok, f"{nome}: {p:.3f}"))
        o.append(t(bx + ww + 8 if p < 0.5 else bx + 10, y + 20, f"{nome} {p:.3f}".replace(".", ","), 15,
                   "ink" if p < 0.5 else "on-color", 600))
    o.append(t(bx, yc + 128, "uscita reale per una foto", 14, "muted"))
    o.append(t(bx, yc + 148, "di buca della validation", 14, "muted"))

    stats = [("2.263.108", "parametri"), ("69", "operatori int8"), ("2,6 MB", "sul disco della board"),
             ("41 ms", "per foto sulla UNO Q")]
    for i, (n, l) in enumerate(stats):
        xx = 64 + i * 372
        o.append(t(xx, 812, n, 40, "ink", 700, DISP))
        o.append(t(xx, 842, l, 17, "ink2"))
    return svg("rete", "".join(o), "Architettura della rete neurale MobileNetV2 con testa a 4 classi")


# ---------------------------------------------------------------------------- 03 blocco
def g_blocco():
    o = [testata("Il mattone della rete: il blocco inverted residual",
                 "17 blocchi in fila. Esempio con i numeri reali di un blocco a 14×14 e 96 canali")]
    yc = 400
    elems = [("ingresso", ["14×14×96"], 36, "panel2", "ink2"),
             ("1×1 espansione", ["14×14×576", "ReLU6"], 120, "panel2", "ink2"),
             ("3×3 depthwise", ["un filtro per canale", "ReLU6"], 120, "accent-soft", "accent"),
             ("1×1 proiezione", ["14×14×96", "lineare"], 36, "panel2", "ink2")]
    x, gap, h = 110, 120, 230
    xs = []
    for i, (nome, sotto, w, fill, st) in enumerate(elems):
        o.append(blocco3d(x, yc, w, h, fill, 14, st))
        o.append(t(x + w / 2 + 7, yc + h / 2 + 40, nome, 19, "ink", 600, anchor="middle"))
        o.append(righe(x + w / 2 + 7, yc + h / 2 + 64, sotto, 15, "ink2", 21, anchor="middle"))
        xs.append((x, w))
        if i < 3:
            o.append(freccia(x + w + 18, yc, x + w + gap - 6, yc, "ink", 2.5, 11))
        x += w + gap
    # somma
    xp = x + 10
    o.append(f'<circle cx="{xp + 26}" cy="{yc}" r="26" fill="{c("panel")}" stroke="{c("ink")}" stroke-width="2.5"/>')
    o.append(t(xp + 26, yc + 10, "+", 30, "ink", 700, anchor="middle"))
    o.append(freccia(xs[-1][0] + xs[-1][1] + 18, yc, xp - 2, yc, "ink", 2.5, 11))
    o.append(freccia(xp + 54, yc, xp + 120, yc, "ink", 2.5, 11))
    o.append(t(xp + 130, yc + 6, "uscita", 19, "ink", 600))
    # scorciatoia
    x0 = xs[0][0] + xs[0][1] / 2
    ytop = yc - h / 2 - 70
    o.append(f'<path d="M{x0} {yc - h / 2 - 16} V{ytop} H{xp + 26} V{yc - 30}" stroke="{c("ink2")}" '
             f'stroke-width="2.5" fill="none" stroke-dasharray="8 6"/>')
    o.append(f'<polygon points="{xp + 26},{yc - 27} {xp + 20},{yc - 40} {xp + 32},{yc - 40}" fill="{c("ink2")}"/>')
    o.append(t((x0 + xp) / 2, ytop - 12, "scorciatoia residua: l'ingresso si somma all'uscita", 16, "ink2",
               anchor="middle"))
    o.append(t(xs[1][0] + xs[1][1] + 39, yc - h / 2 - 34, "stretto → largo → stretto: per questo \"invertito\"",
               15, "muted", anchor="middle"))

    # confronto costi (numeri calcolati: 14x14, 96 canali in e out)
    std = 14 * 14 * 9 * 96 * 96
    sep = 14 * 14 * 9 * 96 + 14 * 14 * 96 * 96
    yy, xx, maxw = 712, 64, 600
    o.append(t(xx, yy - 28, "Moltiplicazioni per uno strato 3×3 da 96 a 96 canali su 14×14", 18, "ink", 600))
    for i, (nome, v, tok) in enumerate([("convoluzione 3×3 normale", std, "norm"),
                                         ("depthwise 3×3 + 1×1", sep, "accent")]):
        y = yy + i * 52
        ww = maxw * v / std
        o.append(r(xx + 250, y, ww, 34, tok, rx=4))
        o.append(t(xx, y + 23, nome, 16, "ink2"))
        o.append(t(xx + 250 + ww + 10, y + 23, f"{v / 1e6:.1f} M".replace(".", ","), 16, "ink", 600, MONO))
    o.append(t(xx + 250 + maxw + 120, yy + 46, f"{std / sep:.1f}×".replace(".", ","), 64, "ink", 700, DISP))
    o.append(t(xx + 250 + maxw + 120, yy + 78, "meno calcoli", 20, "ink2"))

    note = [("Perché MobileNetV2", ["Le convoluzioni depthwise separabili", "costano ~8 volte meno: la rete gira",
                                    "sui 4 core della UNO Q in 41 ms."]),
            ("Perché ReLU6", ["Limita i valori fra 0 e 6: stanno bene", "in 8 bit, per questo la versione int8",
                              "non perde accuratezza (98,0%)."])]
    for i, (tit, rr) in enumerate(note):
        x0n = 1170
        y0n = 240 + i * 150
        o.append(t(x0n, y0n, tit, 19, "ink", 700))
        o.append(righe(x0n, y0n + 28, rr, 16, "ink2", 23))
    return svg("blocco", "".join(o), "Il blocco inverted residual di MobileNetV2 e il risparmio di calcoli")


# ---------------------------------------------------------------------------- 04 addestramento
def g_addestramento():
    o = [testata("Come è stato addestrato",
                 "Dal dataset al file che gira sulla board: sei passi, pochi minuti su una GPU da portatile")]
    passi = [("Dati", "1.485 foto", ["4 classi", "foto web CC BY 4.0", "+ frame del telefono"]),
             ("Preparazione", "1.188 / 297", ["doppioni rimossi (dHash)", "rotazione EXIF", "split 80 / 20"]),
             ("Ritaglio e varianti", "224×224", ["ritaglio centrale", "flip, ±20°, zoom ±15%", "luce e contrasto ±25%"]),
             ("Fase 1 · testa", "10 epoche", ["backbone congelato", "learning rate 1e-3", "5.124 parametri"]),
             ("Fase 2 · fine-tuning", "15 epoche", ["ultimi 40 strati", "learning rate 1e-5", "BatchNorm congelati"]),
             ("Quantizzazione", "22,5 → 2,6 MB", ["int8, ingresso uint8", "300 foto di calibrazione", "nessuna perdita"])]
    bw, gap, x0, y0, bh = 222, 28, 64, 200, 330
    for i, (tit, num, det) in enumerate(passi):
        x = x0 + i * (bw + gap)
        evid = i in (3, 4)
        o.append(r(x, y0, bw, bh, "accent-soft" if evid else "panel", "accent" if evid else "line", 12,
                   2.5 if evid else 1.5))
        o.append(t(x + 20, y0 + 40, f"{i + 1}", 18, "muted", 600, MONO))
        o.append(t(x + 20, y0 + 78, tit, 22, "ink", 700, DISP))
        o.append(righe(x + 20, y0 + 124, det, 16, "ink2", 26))
        o.append(f'<line x1="{x + 20}" y1="{y0 + 232}" x2="{x + bw - 20}" y2="{y0 + 232}" stroke="{c("line")}"/>')
        o.append(t(x + 20, y0 + 286, num, 34 if len(num) < 12 else 27, "ink", 700, DISP))
        if i < 5:
            o.append(freccia(x + bw + 3, y0 + bh / 2, x + bw + gap - 3, y0 + bh / 2, "ink2", 2.2, 9))
    # GPU sotto fasi 4-5
    xa = x0 + 3 * (bw + gap)
    o.append(f'<path d="M{xa} {y0 + bh + 18} v10 h{2 * bw + gap} v-10" stroke="{c("accent")}" '
             f'stroke-width="3" fill="none"/>')
    o.append(t(xa + bw + gap / 2, y0 + bh + 56, "GPU RTX 4050 · TensorFlow 2.20 · WSL2", 16, "ink2", 500,
               anchor="middle"))
    # destinazione
    xd = x0 + 5 * (bw + gap) + bw / 2
    o.append(freccia(xd, y0 + bh + 8, xd, y0 + bh + 70, "ink", 2.5, 11))
    o.append(r(xd - 111, y0 + bh + 78, 222, 54, "ink", rx=10))
    o.append(t(xd, y0 + bh + 112, "UNO Q · ai-edge-litert", 17, "paper", 600, anchor="middle"))

    risult = [("98,0%", "accuratezza sulle 297 foto di validation"),
              ("+0,3", "punti dopo la quantizzazione int8: nessun costo"),
              ("0", "falsi allarmi sulle foto di strada normale")]
    for i, (n, l) in enumerate(risult):
        xx = 64 + i * 420
        o.append(t(xx, 790, n, 48, "ink", 700, DISP))
        o.append(t(xx, 824, l, 17, "ink2"))
    return svg("addestramento", "".join(o), "Pipeline di addestramento del modello in sei passi")


# ---------------------------------------------------------------------------- 05 decisione
def g_decisione():
    o = [testata("Quando una foto diventa una segnalazione",
                 "Tre filtri in fila sulla UNO Q: una foto passa solo se li supera tutti")]
    y = 330
    # foto + modello
    o.append(r(64, y - 70, 150, 140, "panel2", "line", 10))
    o.append(t(139, y - 2, "foto", 22, "ink", 700, DISP, anchor="middle"))
    o.append(t(139, y + 24, "dal telefono", 15, "ink2", anchor="middle"))
    o.append(freccia(218, y, 258, y, "ink", 2.5, 11))
    o.append(r(262, y - 70, 170, 140, "accent-soft", "accent", 10, 2.5))
    o.append(t(347, y - 30, "modello", 22, "ink", 700, DISP, anchor="middle"))
    for i, (tok, p) in enumerate([("buca", 0.98), ("rif", 0.008), ("norm", 0.008), ("cass", 0.004)]):
        o.append(r(284, y - 12 + i * 18, max(3, 120 * p), 12, tok, rx=2))
    o.append(t(347, y + 88, "4 probabilità", 14, "muted", anchor="middle"))
    gates = [("classe diversa da normale", "e confidenza ≥ 0,70"),
             ("stessa classe in 2", "delle ultime 3 foto"),
             ("nessuna segnalazione uguale", "entro 20 m e 60 s")]
    x = 470
    for i, (a, b) in enumerate(gates):
        o.append(freccia(x - 34, y, x - 4, y, "ink", 2.5, 11))
        o.append(f'<polygon points="{x},{y} {x + 120},{y - 92} {x + 240},{y} {x + 120},{y + 92}" '
                 f'fill="{c("panel")}" stroke="{c("ink")}" stroke-width="2"/>')
        o.append(t(x + 120, y - 6, a, 14, "ink", 600, anchor="middle"))
        o.append(t(x + 120, y + 15, b, 14, "ink", 600, anchor="middle"))
        o.append(t(x + 120, y - 104, f"filtro {i + 1}", 14, "muted", 600, MONO, anchor="middle"))
        o.append(freccia(x + 120, y + 94, x + 120, y + 150, "muted", 2, 9))
        o.append(r(x + 60, y + 154, 120, 38, "panel2", rx=19))
        o.append(t(x + 120, y + 179, "scartata", 16, "ink2", 500, anchor="middle"))
        o.append(t(x + 132, y + 126, "no", 14, "muted", 600, MONO))
        x += 280
    o.append(freccia(x - 34, y, x - 4, y, "ink", 2.5, 11))
    o.append(t(x - 28, y - 14, "sì", 14, "ink", 600, MONO))
    o.append(r(x, y - 80, 196, 160, "ink", rx=12))
    o.append(t(x + 98, y - 38, "segnalazione", 22, "paper", 700, DISP, anchor="middle"))
    o.append(righe(x + 98, y - 6, ["+ posizione GPS", "+ sensori MCU", "→ TorinoSegnala"], 15, "paper", 24,
                   anchor="middle"))

    # risultati
    o.append(f'<line x1="64" y1="610" x2="1536" y2="610" stroke="{c("line")}" stroke-width="1.5"/>')
    tiles = [("5 su 6", "errori della validation fermati", "dalla soglia 0,70 (confidenza 50–65%)"),
             ("19", "foto corrette perse sotto soglia:", "il prezzo di pochi falsi allarmi"),
             ("0", "segnalazioni su 178 foto di una", "stanza, nella prova dal vivo")]
    for i, (n, a, b) in enumerate(tiles):
        xx = 64 + i * 500
        o.append(t(xx, 700, n, 56, "ink", 700, DISP))
        o.append(t(xx, 738, a, 18, "ink2"))
        o.append(t(xx, 762, b, 18, "ink2"))
    return svg("decisione", "".join(o), "I tre filtri che trasformano una foto in segnalazione")


# ---------------------------------------------------------------------------- 06 dataset
def g_dataset():
    o = [testata("Il dataset", "1.485 immagini in 4 classi · 80% addestramento, 20% validation")]
    dati = [("buca", 72, 18, "buca", "keremberke/pothole-segmentation · CC BY 4.0"),
            ("rifiuti", 480, 120, "rif", "TACO / waste_littering · CC BY 4.0"),
            ("cassonetto pieno", 480, 120, "cass", "Garbage_Bin_overflow_images · CC BY 4.0"),
            ("normale", 156, 39, "norm", "frame del telefono BusSense, raccolti sulla board")]
    x0, xw, y0, bh, gap = 480, 790, 210, 64, 58
    vmax = 600
    for k in range(0, 601, 100):
        xx = x0 + xw * k / vmax
        o.append(f'<line x1="{xx}" y1="{y0 - 14}" x2="{xx}" y2="{y0 + 4 * (bh + gap) - gap + 10}" '
                 f'stroke="{c("line")}" stroke-width="1"/>')
        o.append(t(xx, y0 + 4 * (bh + gap) - gap + 36, k, 15, "muted", 400, MONO, anchor="middle"))
    for i, (nome, tr, va, tok, fonte) in enumerate(dati):
        y = y0 + i * (bh + gap)
        wt, wv = xw * tr / vmax, xw * va / vmax
        o.append(t(64, y + 28, nome, 22, "ink", 600))
        o.append(t(64, y + 54, fonte, 13, "muted"))
        o.append(rt(x0, y, wt - 1, bh, tok, f"{nome}: {tr} foto di addestramento"))
        o.append(rt(x0 + wt + 1, y, wv - 1, bh, tok, f"{nome}: {va} foto di validation", 0.45))
        o.append(t(x0 + wt + wv + 14, y + 40, f"{tr + va}", 26, "ink", 700, DISP))
        o.append(t(x0 + wt + wv + 80, y + 40, f"{tr} + {va}", 16, "ink2", 400, MONO))
    # legenda
    o.append(r(1230, 158, 24, 16, "ink2", rx=3) + t(1262, 172, "addestramento", 15, "ink2"))
    o.append(f'<rect x="1390" y="158" width="24" height="16" rx="3" fill="{c("ink2")}" opacity="0.45"/>'
             + t(1422, 172, "validation", 15, "ink2"))
    o.append(r(64, 726, 1472, 120, "accent-soft", rx=12))
    o.append(t(88, 766, "Le buche sono 6,7 volte meno delle altre classi", 22, "ink", 700))
    o.append(t(88, 798, "In addestramento ogni buca pesa 2,27 contro 0,34 di rifiuti e cassonetti, così il modello "
                        "non impara a ignorarle.", 17, "ink2"))
    o.append(t(88, 824, "Il rimedio vero è avere più foto di buche, meglio se riprese dal bus.", 17, "ink2"))
    return svg("dataset", "".join(o), "Composizione del dataset per classe")


# ---------------------------------------------------------------------------- 07 matrice
def g_matrice():
    o = [testata("Dove sbaglia", "Matrice di confusione sulle 297 foto di validation · modello int8 della board")]
    nomi = ["buca", "rifiuti", "cassonetto", "normale"]
    toks = ["buca", "rif", "cass", "norm"]
    m = [[18, 0, 0, 0], [2, 116, 2, 0], [0, 2, 118, 0], [0, 0, 0, 39]]
    cs, x0, y0 = 128, 330, 240
    o.append(t(x0 + 2 * cs, y0 - 52, "classe predetta dal modello", 17, "ink2", 600, anchor="middle"))
    o.append(t(150, y0 + 2 * cs, "classe vera", 17, "ink2", 600, anchor="middle",
               extra=f'transform="rotate(-90 150 {y0 + 2 * cs})"'))
    rampa = [(0.0, "panel2"), (0.005, "s100"), (0.02, "s200"), (0.5, "s400"), (0.9, "s650")]
    for j, n in enumerate(nomi):
        o.append(t(x0 + j * cs + cs / 2, y0 - 16, n, 17, "ink", 600, anchor="middle"))
    for i, n in enumerate(nomi):
        o.append(r(x0 - 24, y0 + i * cs + cs / 2 - 10, 12, 20, toks[i], rx=3))
        o.append(t(x0 - 34, y0 + i * cs + cs / 2 + 6, n, 17, "ink", 600, anchor="end"))
        tot = sum(m[i])
        for j in range(4):
            v = m[i][j]
            frac = v / tot
            tok = [tk for soglia, tk in rampa if frac >= soglia][-1]
            scuro = tok in ("s400", "s650")
            o.append(f'<rect x="{x0 + j * cs + 2}" y="{y0 + i * cs + 2}" width="{cs - 4}" height="{cs - 4}" rx="6" '
                     f'fill="{c(tok)}"><title>{n} → {nomi[j]}: {v} foto ({frac:.0%})</title></rect>')
            if v:
                o.append(t(x0 + j * cs + cs / 2, y0 + i * cs + cs / 2 + 6, v, 30, "on-color" if scuro else "ink",
                           700, DISP, anchor="middle"))
                o.append(t(x0 + j * cs + cs / 2, y0 + i * cs + cs / 2 + 30, f"{frac:.0%}", 14,
                           "on-color" if scuro else "ink2", 400, MONO, anchor="middle"))
            else:
                o.append(t(x0 + j * cs + cs / 2, y0 + i * cs + cs / 2 + 8, "·", 22, "muted", anchor="middle"))
    # tabella precision/recall
    xt = 980
    pr = [("buca", 90.0, 100.0, "buca"), ("rifiuti", 98.3, 96.7, "rif"), ("cassonetto", 98.3, 98.3, "cass"),
          ("normale", 100.0, 100.0, "norm")]
    o.append(t(xt + 200, y0 - 16, "precision", 16, "ink2", 600, anchor="end"))
    o.append(t(xt + 340, y0 - 16, "recall", 16, "ink2", 600, anchor="end"))
    for i, (n, p, rc, tok) in enumerate(pr):
        yy = y0 + i * 62 + 30
        o.append(r(xt, yy - 15, 12, 20, tok, rx=3))
        o.append(t(xt + 22, yy, n, 18, "ink", 600))
        o.append(t(xt + 200, yy, f"{p:.1f}%".replace(".", ","), 18, "ink", 500, MONO, anchor="end"))
        o.append(t(xt + 340, yy, f"{rc:.1f}%".replace(".", ","), 18, "ink", 500, MONO, anchor="end"))
    o.append(righe(xt, y0 + 310, ["precision: quando dice X, quanto spesso è X", "recall: delle foto X, quante ne trova"],
                   15, "muted", 22))
    o.append(r(64, 790, 1472, 70, "accent-soft", rx=12))
    o.append(t(88, 832, "6 errori su 297, tutti fra rifiuti e cassonetto o rifiuti scambiati per buca. "
                        "Nessuna foto di strada normale segnalata.", 19, "ink", 500))
    return svg("matrice", "".join(o), "Matrice di confusione del modello sulla validation")


# ---------------------------------------------------------------------------- 08 soglia
def g_soglia():
    o = [testata("Quanto essere sicuri prima di segnalare",
                 "Al crescere della soglia si segnala meno ma si sbaglia meno · 297 foto di validation")]
    soglie = [0.50, 0.60, 0.70, 0.80, 0.90, 0.95]
    prec = [97.6, 98.8, 99.6, 99.6, 100.0, 100.0]
    seg = [254, 246, 235, 225, 189, 137]
    rec = [round(s * p / 100 / 258 * 100, 1) for s, p in zip(seg, prec)]
    x0, x1, y0, y1 = 150, 1180, 190, 720
    sx = lambda v: x0 + (v - 0.5) / 0.45 * (x1 - x0)
    sy = lambda v: y1 - (v - 50) / 50 * (y1 - y0)
    for v in range(50, 101, 10):
        o.append(f'<line x1="{x0}" y1="{sy(v)}" x2="{x1}" y2="{sy(v)}" stroke="{c("line")}" stroke-width="1"/>')
        o.append(t(x0 - 14, sy(v) + 5, f"{v}%", 15, "muted", 400, MONO, anchor="end"))
    for s in soglie:
        o.append(t(sx(s), y1 + 30, f"{s:.2f}".replace(".", ","), 15, "muted", 400, MONO, anchor="middle"))
    o.append(t((x0 + x1) / 2, y1 + 64, "soglia di confidenza (BUSSENSE_VISION_CONF)", 16, "ink2", 600, anchor="middle"))
    # soglia scelta
    o.append(f'<line x1="{sx(0.7)}" y1="{y0 - 10}" x2="{sx(0.7)}" y2="{y1}" stroke="{c("accent")}" '
             f'stroke-width="3" stroke-dasharray="7 5"/>')
    o.append(r(sx(0.7) - 74, y0 - 44, 148, 30, "accent", rx=15))
    o.append(t(sx(0.7), y0 - 23, "in uso: 0,70", 16, "ink", 700, anchor="middle"))
    serie = [("segnalazioni corrette", prec, "buca"), ("foto con un problema trovate", rec, "cass")]
    for nome, vals, tok in serie:
        pts = " ".join(f"{sx(s):.1f},{sy(v):.1f}" for s, v in zip(soglie, vals))
        o.append(f'<polyline points="{pts}" fill="none" stroke="{c(tok)}" stroke-width="3"/>')
        for s, v in zip(soglie, vals):
            o.append(f'<circle cx="{sx(s):.1f}" cy="{sy(v):.1f}" r="7" fill="{c(tok)}" stroke="{c("paper")}" '
                     f'stroke-width="2.5"><title>{nome}, soglia {s:.2f}: {v:.1f}%</title></circle>')
    # etichette dirette
    o.append(t(sx(0.95) + 16, sy(prec[-1]) + 6, "segnalazioni corrette", 17, "ink", 600))
    o.append(t(sx(0.95) + 16, sy(prec[-1]) + 28, "100%", 16, "ink2", 400, MONO))
    o.append(t(sx(0.95) + 16, sy(rec[-1]) + 6, "foto con un problema", 17, "ink", 600))
    o.append(t(sx(0.95) + 16, sy(rec[-1]) + 28, f"trovate · {rec[-1]:.0f}%", 16, "ink2", 400, MONO))
    o.append(t(sx(0.7) + 12, sy(rec[2]) + 34, f"{rec[2]:.1f}%".replace(".", ","), 16, "ink", 600, MONO))
    o.append(t(sx(0.7) + 12, sy(prec[2]) + 30, f"{prec[2]:.1f}%".replace(".", ","), 16, "ink", 600, MONO))
    # legenda
    for i, (nome, _, tok) in enumerate(serie):
        o.append(f'<line x1="{150 + i * 330}" y1="822" x2="{186 + i * 330}" y2="822" stroke="{c(tok)}" stroke-width="3"/>'
                 f'<circle cx="{168 + i * 330}" cy="822" r="6" fill="{c(tok)}"/>')
        o.append(t(196 + i * 330, 828, nome, 16, "ink2"))
    return svg("soglia", "".join(o), "Effetto della soglia di confidenza su segnalazioni corrette e problemi trovati")


# ---------------------------------------------------------------------------- 09 board
def g_board():
    o = [testata("Piccolo e veloce abbastanza per la board",
                 "Stesso modello in tre formati, e quanto ci mette sulla UNO Q")]
    fmt = [("Keras float32", 22.5, "97,6%"), ("TFLite float32", 8.7, "97,6%"), ("TFLite int8 · sulla board", 2.6, "98,0%")]
    x0, xw, y0 = 380, 330, 240
    o.append(t(64, 200, "Dimensione del file", 20, "ink", 700))
    for i, (n, mb, acc) in enumerate(fmt):
        y = y0 + i * 92
        ww = xw * mb / 22.5
        tok = "accent" if i == 2 else "norm"
        o.append(t(64, y + 32, n, 18, "ink", 600 if i == 2 else 400))
        o.append(r(x0, y, ww, 46, tok, rx=4))
        o.append(t(x0 + ww + 12, y + 31, f"{mb:.1f} MB".replace(".", ","), 18, "ink", 600, MONO))
        o.append(t(64, y + 56, f"accuratezza {acc}", 14, "muted"))
    o.append(t(64, 560, "−88% di spazio, accuratezza invariata", 22, "ink", 700, DISP))

    # tempi contro budget
    xb, wb, yb = 900, 600, 240
    o.append(t(xb, 200, "Millisecondi per foto sulla UNO Q", 20, "ink", 700))
    tempi = [("benchmark", 41, "accent"), ("in esercizio", 82, "accent"),
             ("tempo disponibile", 1000, "line")]
    for i, (n, ms, tok) in enumerate(tempi):
        y = yb + i * 92
        ww = wb * ms / 1000
        o.append(r(xb, y, max(ww, 4), 46, tok, rx=4))
        o.append(t(xb + max(ww, 4) + 12 if i < 2 else xb + 14, y + 31, f"{ms} ms", 18, "ink", 600, MONO))
        o.append(t(xb, y + 66, n if i < 2 else "tempo disponibile: 1 foto al secondo (modalità demo)", 14, "muted"))
    o.append(t(xb, 560, "12 volte più veloce del necessario", 22, "ink", 700, DISP))

    o.append(r(64, 650, 1472, 130, "panel", "line", 12))
    cose = [("4 core Cortex-A53", "nessuna NPU usata: tutto in CPU"), ("ai-edge-litert 2.3.0", "pochi MB, niente TensorFlow"),
            ("Python 3.13 · Debian 13", "nel container dell'app App Lab"), ("Coda da 1 foto", "se resta indietro tiene l'ultima")]
    for i, (a, b) in enumerate(cose):
        xx = 96 + i * 362
        o.append(t(xx, 712, a, 21, "ink", 700))
        o.append(t(xx, 742, b, 16, "ink2"))
    return svg("board", "".join(o), "Dimensioni del modello e tempi di inferenza sulla UNO Q")


# ---------------------------------------------------------------------------- 10 classe normale
def g_normale():
    o = [testata("Perché serve la classe \"normale\"",
                 "Un classificatore sceglie sempre una delle classi che conosce. Senza \"niente\", inventa.")]
    col = [("v1 · 3 classi", "11", "falsi allarmi in 7 minuti", ["telefono puntato su una stanza:",
                                                                 "tavoli e zaini scambiati per", "cassonetti e rifiuti, fino al 98%"],
            "muted"),
           ("v2 · + normale", "0", "segnalazioni su 178 foto", ["stessa stanza, stesso telefono:",
                                                               "195 frame di esempio bastano", "a insegnare cos'è \"niente\""],
            "accent")]
    for i, (tit, n, sub, det, tok) in enumerate(col):
        x = 64 + i * 752
        o.append(r(x, 200, 720, 520, "panel", "line", 16))
        o.append(r(x, 200, 720, 10, tok, rx=0))
        o.append(t(x + 40, 266, tit, 26, "ink", 700, DISP))
        o.append(t(x + 40, 450, n, 170, "ink", 700, DISP))
        o.append(t(x + 40, 500, sub, 26, "ink", 600))
        o.append(righe(x + 40, 570, det, 19, "ink2", 30))
    o.append(t(64, 790, "Le 11 segnalazioni della v1 sono rimaste sulla board e non sono mai arrivate alla piattaforma.",
               18, "muted"))
    return svg("normale", "".join(o), "Confronto fra il modello senza e con la classe normale nella prova dal vivo")


GRAFICHE = {
    "01_sistema": g_sistema, "02_rete_neurale": g_rete, "03_blocco_inverted_residual": g_blocco,
    "04_addestramento": g_addestramento, "05_decisione_sulla_board": g_decisione, "06_dataset": g_dataset,
    "07_matrice_confusione": g_matrice, "08_soglia": g_soglia, "09_modello_sulla_board": g_board,
    "10_classe_normale": g_normale,
}


def main():
    (QUI / "sorgenti").mkdir(exist_ok=True)
    (QUI / "svg").mkdir(exist_ok=True)
    for nome, f in GRAFICHE.items():
        s = f()
        (QUI / "sorgenti" / f"{nome}.svg").write_text(s, encoding="utf-8")
        # per le slide: valori chiari al posto dei var()
        piatto = re.sub(r"var\(--[\w-]+, (#[0-9a-fA-F]{6})\)", r"\1", s)
        (QUI / "svg" / f"{nome}.svg").write_text(piatto, encoding="utf-8")
        print(nome)


if __name__ == "__main__":
    main()
