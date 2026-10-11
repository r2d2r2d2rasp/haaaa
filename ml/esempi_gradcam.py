"""Foto della validation analizzate dal modello, con la zona che ha deciso la risposta.

Per la presentazione: per ogni classe sceglie foto MAI viste in addestramento, le fa
classificare dal modello int8 con il codice della board (bussense.classifier) e disegna
sopra la mappa Grad-CAM, cioe dove la rete ha "guardato" per decidere, piu il riquadro
della zona piu calda.

Il riquadro NON e una detection: il modello e un classificatore e non e stato addestrato
con riquadri. Grad-CAM ricava la zona dai gradienti dell'ultimo strato convoluzionale
(7x7), quindi e una localizzazione approssimativa, utile a mostrare che la rete guarda
la buca e non lo sfondo.

Uso (da WSL, nella cartella ml/):
    python esempi_gradcam.py
Scrive in docs/img/presentazione/esempi/.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import deque
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import numpy as np
import tensorflow as tf
from PIL import Image, ImageDraw, ImageFont, ImageOps
from tensorflow import keras

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "unoq-app" / "python"))
from bussense.classifier import Classifier, preprocess  # noqa: E402

COLORI = {"buca": "#2a78d6", "rifiuti": "#1baf7a", "cassonetto_pieno": "#eb6834", "normale": "#7d828a"}
NOMI = {"buca": "BUCA", "rifiuti": "RIFIUTI", "cassonetto_pieno": "CASSONETTO PIENO", "normale": "NORMALE"}
INK, PAPER, MUTED = "#1e2227", "#f7f6f2", "#5b6068"
FONT_DIR = Path("/usr/share/fonts/truetype/ibm-plex")


def font(nome: str, size: int):
    try:
        return ImageFont.truetype(str(FONT_DIR / nome), size)
    except OSError:
        return ImageFont.load_default()


def hex_rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def modello_cam(modello: keras.Model):
    """Ricostruisce il grafo per avere sia le mappe 7x7x1280 sia le probabilita."""
    backbone = modello.get_layer("mobilenetv2_1.00_224")
    norm, pool, dense = (modello.get_layer(n) for n in ("normalizza", "pooling", "classe"))
    ingresso = keras.Input(shape=modello.input_shape[1:])
    mappe = backbone(norm(ingresso), training=False)
    return keras.Model(ingresso, [mappe, dense(pool(mappe))])


def gradcam(cam_model, img_uint8: np.ndarray, classe: int) -> np.ndarray:
    x = tf.convert_to_tensor(img_uint8[None].astype(np.float32))
    with tf.GradientTape() as tape:
        mappe, prob = cam_model(x)
        punteggio = prob[:, classe]
    grad = tape.gradient(punteggio, mappe)[0]          # 7x7x1280
    pesi = tf.reduce_mean(grad, axis=(0, 1))           # importanza di ogni canale
    cam = tf.nn.relu(tf.reduce_sum(mappe[0] * pesi, axis=-1)).numpy()
    return cam / cam.max() if cam.max() > 0 else cam


def riquadro(cam: np.ndarray, lato: int, soglia: float = 0.6):
    """Riquadro della zona calda piu grande (componente connessa sopra soglia)."""
    n = 28
    piccola = np.asarray(Image.fromarray((cam * 255).astype(np.uint8)).resize((n, n), Image.BILINEAR)) / 255
    mask = piccola >= soglia
    visti = np.zeros_like(mask)
    migliore = []
    for i in range(n):
        for j in range(n):
            if mask[i, j] and not visti[i, j]:
                comp, coda = [], deque([(i, j)])
                visti[i, j] = True
                while coda:
                    a, b = coda.popleft()
                    comp.append((a, b))
                    for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        u, v = a + da, b + db
                        if 0 <= u < n and 0 <= v < n and mask[u, v] and not visti[u, v]:
                            visti[u, v] = True
                            coda.append((u, v))
                if len(comp) > len(migliore):
                    migliore = comp
    if not migliore:
        return None
    ys, xs = zip(*migliore)
    s = lato / n
    return (min(xs) * s, min(ys) * s, (max(xs) + 1) * s, (max(ys) + 1) * s)


def tratteggio(d: ImageDraw.ImageDraw, box, colore, w=4, trat=16):
    x0, y0, x1, y1 = box
    for (a, b, c, e) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        lung = max(abs(c - a), abs(e - b))
        passi = max(1, int(lung // trat))
        for k in range(0, passi, 2):
            t0, t1 = k / passi, min(1, (k + 1) / passi)
            d.line((a + (c - a) * t0, b + (e - b) * t0, a + (c - a) * t1, b + (e - b) * t1), fill=colore, width=w)


def vista(f: Path, lato: int = 512) -> Image.Image:
    """Lo stesso ritaglio quadrato centrale del modello, ma dalla foto originale a piena risoluzione."""
    im = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
    w, h = im.size
    s = min(w, h)
    x0, y0 = (w - s) // 2, (h - s) // 2
    return im.crop((x0, y0, x0 + s, y0 + s)).resize((lato, lato), Image.LANCZOS)


def annota(sfondo: Image.Image, cam, classe, conf, lato=512, vera=None):
    base = sfondo.convert("RGBA")
    col = hex_rgb(COLORI[classe])
    if cam is not None:
        grande = np.asarray(Image.fromarray((cam * 255).astype(np.uint8)).resize((lato, lato), Image.BICUBIC)) / 255
        alfa = np.clip((grande - 0.3) / 0.7, 0, 1) ** 1.3 * 0.62
        strato = np.zeros((lato, lato, 4), np.uint8)
        strato[..., :3] = col
        strato[..., 3] = (alfa * 255).astype(np.uint8)
        base = Image.alpha_composite(base, Image.fromarray(strato, "RGBA"))
    d = ImageDraw.Draw(base)
    if cam is not None and (b := riquadro(cam, lato)):
        tratteggio(d, (b[0] - 1, b[1] - 1, b[2] + 1, b[3] + 1), "#ffffff", w=7)  # bordo per il contrasto
        tratteggio(d, b, COLORI[classe], w=4)
    # cornice e etichetta
    d.rectangle((0, 0, lato - 1, lato - 1), outline=COLORI[classe], width=8)
    testo = f"{NOMI[classe]}  {conf * 100:.0f}%"
    f = font("IBMPlexSansCondensed-Bold.ttf", 30)
    tw = d.textlength(testo, font=f)
    d.rounded_rectangle((14, 14, 14 + tw + 28, 62), radius=6, fill=COLORI[classe])
    d.text((28, 17), testo, font=f, fill="#ffffff")
    if vera and vera != classe:
        g = font("IBMPlexSans-SemiBold.ttf", 20)
        t2 = f"in realta: {NOMI[vera].lower()}"
        d.rounded_rectangle((14, 70, 14 + d.textlength(t2, font=g) + 24, 102), radius=5, fill=INK)
        d.text((26, 73), t2, font=g, fill="#ffffff")
    if classe == "normale":
        g = font("IBMPlexSans-SemiBold.ttf", 20)
        t2 = "nessuna segnalazione"
        d.rounded_rectangle((14, 70, 14 + d.textlength(t2, font=g) + 24, 102), radius=5, fill=INK)
        d.text((26, 73), t2, font=g, fill="#ffffff")
    return base.convert("RGB")


def griglia(righe: list[tuple[str, list[Image.Image]]], titolo: str, sotto: str, nota: str) -> Image.Image:
    lato, gap, mx, header, label_w = 512, 18, 56, 170, 0
    cols = max(len(r[1]) for r in righe)
    W = mx * 2 + cols * lato + (cols - 1) * gap
    H = header + len(righe) * (lato + 64) + 90
    out = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(out)
    d.text((mx, 44), titolo, font=font("IBMPlexSansCondensed-Bold.ttf", 54), fill=INK)
    d.text((mx, 110), sotto, font=font("IBMPlexSans-Regular.ttf", 26), fill=MUTED)
    y = header
    for nome, imgs in righe:
        d.text((mx, y + 8), nome, font=font("IBMPlexSans-SemiBold.ttf", 28), fill=INK)
        y += 52
        for k, im in enumerate(imgs):
            out.paste(im, (mx + k * (lato + gap), y))
        y += lato + 12
    d.text((mx, H - 60), nota, font=font("IBMPlexSans-Regular.ttf", 20), fill=MUTED)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dati", type=Path, default=Path("data_prepared/val"))
    p.add_argument("--modello", type=Path, default=Path("modello"))
    p.add_argument("--out", type=Path, default=ROOT / "docs" / "img" / "presentazione" / "esempi")
    p.add_argument("--per-classe", type=int, default=4)
    p.add_argument("--normale", nargs="*", default=[], help="file di val/normale da includere (senza persone)")
    p.add_argument("--candidati", type=int, default=0,
                   help="invece degli esempi, scrive un foglio con N candidati numerati per classe")
    p.add_argument("--scelte", nargs="*", default=[],
                   help="indici dei candidati da usare, es. rifiuti=0,3,7,9 (default: distribuiti)")
    a = p.parse_args()
    scelte = {k: [int(i) for i in v.split(",")] for k, v in (x.split("=") for x in a.scelte)}

    clf = Classifier(a.modello / "modello_int8.tflite", a.modello / "labels.txt")
    cam_model = modello_cam(keras.models.load_model(a.modello / "modello.keras"))
    a.out.mkdir(parents=True, exist_ok=True)

    risultati = {}  # classe vera -> [(file, predetta, conf)]
    for vera in clf.labels:
        for f in sorted((a.dati / vera).glob("*.jpg")):
            pr = clf.probs(f.read_bytes())
            risultati.setdefault(vera, []).append((f, clf.labels[int(pr.argmax())], float(pr.max())))

    righe, errori = [], []
    for vera in ("buca", "rifiuti", "cassonetto_pieno"):
        giuste = sorted([r for r in risultati[vera] if r[1] == vera and r[2] >= 0.85], key=lambda r: -r[2])
        errori += [(vera, r) for r in risultati[vera] if r[1] != vera]
        if a.candidati:
            imgs = []
            for i in np.linspace(0, len(giuste) - 1, a.candidati).round().astype(int):
                f, pred, conf = giuste[i]
                img = preprocess(Image.open(f), clf.size)
                im = annota(vista(f, 256), gradcam(cam_model, img, clf.labels.index(pred)), pred, conf, lato=256)
                ImageDraw.Draw(im).text((10, 220), f"#{i}", font=font("IBMPlexMono-SemiBold.ttf", 26), fill="#ffff00")
                imgs.append(im)
            cols = 6
            foglio = Image.new("RGB", (cols * 262, ((len(imgs) + cols - 1) // cols) * 262), PAPER)
            for k, im in enumerate(imgs):
                foglio.paste(im, ((k % cols) * 262, (k // cols) * 262))
            foglio.save(a.out / f"candidati_{vera}.jpg", quality=85)
            print(f"{vera}: {len(giuste)} corrette, foglio candidati scritto")
            continue
        # esempi distribuiti lungo la fascia di confidenza, non solo i piu facili
        idx = scelte.get(vera) or np.linspace(0, len(giuste) - 1, a.per_classe).round().astype(int)
        imgs = []
        for k, i in enumerate(idx):
            f, pred, conf = giuste[i]
            img = preprocess(Image.open(f), clf.size)
            im = annota(vista(f), gradcam(cam_model, img, clf.labels.index(pred)), pred, conf)
            im.save(a.out / f"{vera}_{k + 1}.jpg", quality=92)
            imgs.append(im)
        righe.append((NOMI[vera].capitalize() if vera != "cassonetto_pieno" else "Cassonetto pieno", imgs))
        print(f"{vera}: {len(giuste)} corrette con confidenza >= 85%, esempi salvati")

    if a.candidati:
        return 0
    nota = ("Foto di validation, mai viste in addestramento. Etichetta e confidenza: modello int8 della UNO Q. "
            "Zona colorata e riquadro: Grad-CAM. Immagini: Roboflow Universe e TACO, CC BY 4.0.")
    griglia(righe, "Cosa vede il modello",
            "Classe riconosciuta, confidenza e zona dell'immagine che ha deciso la risposta",
            nota).save(a.out / "griglia_rilevamenti.png", optimize=True)

    if errori:
        imgs = []
        for k, (vera, (f, pred, conf)) in enumerate(sorted(errori, key=lambda e: -e[1][2])[:4]):
            img = preprocess(Image.open(f), clf.size)
            im = annota(vista(f), gradcam(cam_model, img, clf.labels.index(pred)), pred, conf, vera=vera)
            im.save(a.out / f"errore_{k + 1}.jpg", quality=92)
            imgs.append(im)
        griglia([("Errori del modello sulla validation", imgs)], "Dove sbaglia",
                 f"{len(errori)} errori su {sum(len(v) for v in risultati.values())} foto di validation · "
                 f"{sum(1 for _, r in errori if r[2] < 0.70)} sotto la soglia 0,70, quindi sulla board "
                 f"non diventano segnalazioni",
                 nota).save(a.out / "griglia_errori.png", optimize=True)
        print(f"errori: {len(errori)} -> " + ", ".join(f"{v}->{r[1]}" for v, r in errori))

    for k, nome in enumerate(a.normale):
        f = a.dati / "normale" / nome
        pr = clf.probs(f.read_bytes())
        pred, conf = clf.labels[int(pr.argmax())], float(pr.max())
        annota(vista(f), None, pred, conf).save(a.out / f"normale_{k + 1}.jpg", quality=92)
        print(f"normale {nome}: {pred} {conf:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
