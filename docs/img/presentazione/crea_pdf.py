"""Unisce copertina, grafiche e foto contrassegnate in un unico PDF vettoriale 16:9.

Le grafiche restano vettoriali (testo nitido, font incorporati); le foto sono JPEG dentro la pagina.
Serve rsvg-convert con i font IBM Plex (Ubuntu: apt install librsvg2-bin fonts-ibm-plex) e Pillow.

    python crea_pdf.py      # -> BusSense_modello_visione.pdf
"""
import base64
import io
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

import genera as g

QUI = Path(__file__).resolve().parent
OUT = QUI / "BusSense_modello_visione.pdf"


def piatto(s: str) -> str:
    return re.sub(r"var\(--[\w-]+, (#[0-9a-fA-F]{6})\)", r"\1", s)


def copertina() -> str:
    o = [g.r(0, 0, 1600, 12, "accent", rx=0)]
    o.append(g.t(96, 250, "BUSSENSE · HACKTURIN 2026", 20, "muted", 600, g.MONO, extra='letter-spacing="3"'))
    o.append(g.t(96, 360, "Il modello che riconosce", 92, "ink", 700, g.DISP))
    o.append(g.t(96, 462, "buche e rifiuti", 92, "ink", 700, g.DISP))
    o.append(g.t(96, 530, "Rete neurale MobileNetV2 int8 che gira sulla Arduino UNO Q, dentro il POD sul bus",
                 26, "ink2"))
    # striscia di mezzeria: il giallo della segnaletica
    for k in range(8):
        o.append(g.r(96 + k * 180, 590, 110, 14, "accent", rx=2))
    numeri = [("98,0%", "accuratezza su foto mai viste"), ("41 ms", "per foto sulla UNO Q"),
              ("2,6 MB", "il modello sulla board"), ("0", "falsi allarmi dal vivo")]
    for i, (n, l) in enumerate(numeri):
        x = 96 + i * 360
        o.append(g.t(x, 730, n, 60, "ink", 700, g.DISP))
        o.append(g.t(x, 768, l, 20, "ink2"))
    return g.svg("copertina", "".join(o), "Copertina")


def pagina_foto(titolo: str, sotto: str, img: Path, nota: str) -> str:
    """Pagina 16:9 con una foto (o griglia) centrata sotto il titolo."""
    im = Image.open(img).convert("RGB")
    box_w, box_h, y0 = 1472, 900 - 160 - 70, 160
    scala = min(box_w / im.width, box_h / im.height)
    w, h = im.width * scala, im.height * scala
    im.thumbnail((2400, 2400))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    dati = base64.b64encode(buf.getvalue()).decode()
    x, y = 64 + (box_w - w) / 2, y0 + (box_h - h) / 2
    corpo = (g.testata(titolo, sotto)
             + f'<image x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
               f'href="data:image/jpeg;base64,{dati}"/>'
             + g.t(64, 868, nota, 15, "muted"))
    return g.svg(img.stem, corpo, titolo)


def jpeg_b64(img: Path, lato: int = 1000) -> str:
    im = Image.open(img).convert("RGB")
    im.thumbnail((lato, lato))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def pagina_quattro(titolo: str, sotto: str, imgs: list[Path], nota: str) -> str:
    """Quattro foto contrassegnate in fila, grandi: una pagina per classe."""
    lato, gap, y = 350, 24, 300
    corpo = g.testata(titolo, sotto)
    for k, f in enumerate(imgs):
        x = 64 + k * (lato + gap)
        corpo += (f'<image x="{x}" y="{y}" width="{lato}" height="{lato}" '
                  f'href="data:image/jpeg;base64,{jpeg_b64(f)}"/>')
    corpo += g.t(64, 868, nota, 15, "muted")
    return g.svg(imgs[0].stem, corpo, titolo)


def main():
    esempi = QUI / "esempi"
    fonte = "Foto di validation, mai viste in addestramento · Roboflow Universe e TACO, CC BY 4.0"
    gradcam = ("Etichetta e confidenza: modello int8 della UNO Q · zona colorata e riquadro: Grad-CAM, "
               "dove la rete ha guardato (non è un rilevamento)")
    pagine = [
        copertina(),
        g.g_sistema(), g.g_rete(), g.g_blocco(), g.g_addestramento(),
        pagina_foto("Le curve di addestramento", "Training e validation salgono insieme: nessun overfitting",
                    QUI.parent / "modello_v2_training.png", "10 epoche solo testa, poi 15 di fine-tuning (riga tratteggiata)"),
        g.g_dataset(), g.g_matrice(),
        pagina_quattro("Buche riconosciute", "La zona che ha deciso la risposta cade sulla buca",
                       [esempi / f"buca_{k}.jpg" for k in range(1, 5)], gradcam),
        pagina_quattro("Rifiuti riconosciuti", "La rete guarda l'oggetto e anche il terreno intorno",
                       [esempi / f"rifiuti_{k}.jpg" for k in range(1, 5)], gradcam),
        pagina_quattro("Cassonetti pieni riconosciuti", "Anche di notte, sfocati o in bianco e nero",
                       [esempi / f"cassonetto_pieno_{k}.jpg" for k in range(1, 5)], fonte),
        pagina_quattro("Dove sbaglia", "6 errori su 297 foto · 5 sotto la soglia 0,70, quindi sulla board scartati",
                       [esempi / f"errore_{k}.jpg" for k in range(1, 5)],
                       "I primi due nel dataset sono \"cassonetto pieno\", ma nella foto ci sono cumuli di rifiuti e "
                       "nessun cassonetto: l'errore potrebbe essere dell'etichetta."),
        g.g_soglia(), g.g_decisione(), g.g_normale(), g.g_board(),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for i, s in enumerate(pagine):
            f = Path(tmp) / f"p{i:02d}.svg"
            f.write_text(piatto(s), encoding="utf-8")
            files.append(str(f))
        subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(OUT), *files], check=True)
    print(f"{OUT.name}: {len(pagine)} pagine, {OUT.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
