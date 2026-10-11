"""Valuta il modello sulla validation: Keras contro .tflite int8.

Risponde a tre domande, nell'ordine in cui contano:

  1. Quanto costa la quantizzazione? Confronta l'accuratezza del modello
     Keras con quella del .tflite int8 che finisce davvero sulla board. Un
     calo di 1-2 punti e normale; se e molto piu grande va rifatto l'export
     con piu immagini di calibrazione.

  2. Quali classi confonde? La matrice di confusione dice dove sbaglia. Per
     BusSense l'errore grave e il falso allarme: segnalare una buca dove c'e
     solo asfalto riempie la piattaforma di segnalazioni inutili.

  3. A che soglia di confidenza conviene tagliare? Il modello restituisce
     sempre una probabilita; accettare solo le previsioni sopra una soglia
     riduce gli errori ma lascia passare meno segnalazioni. La tabella finale
     mostra questo scambio, per scegliere BUSSENSE_VISION_CONF sulla UNO Q.

Le immagini passano dal preprocessing della board (bussense/classifier.py) e
i .tflite girano attraverso la stessa classe Classifier della UNO Q: i numeri
sono quelli che si otterranno sul bus, a parita di immagini.

Uso:
    python evaluate.py
    python evaluate.py --solo-tflite
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
from PIL import Image
from tensorflow import keras

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "unoq-app" / "python"))
from bussense.classifier import Classifier, preprocess  # noqa: E402


def carica_immagini(cartella: Path, classi: list[str], img_size: int):
    """Carica la validation come la vede la board: uint8 0..255, ritagliata e ridimensionata."""
    immagini, etichette, percorsi = [], [], []
    for indice, classe in enumerate(classi):
        for percorso in sorted((cartella / classe).glob("*.jpg")):
            immagini.append(preprocess(Image.open(percorso), img_size))
            etichette.append(indice)
            percorsi.append(percorso)
    if not immagini:
        raise SystemExit(f"ERRORE: nessuna immagine in {cartella}")
    return np.stack(immagini), np.array(etichette), percorsi


def predici_tflite(percorso_modello: Path, etichette: Path, percorsi: list[Path]) -> np.ndarray:
    """Esegue il .tflite sui JPEG con il codice della UNO Q, una foto alla volta."""
    clf = Classifier(percorso_modello, etichette)
    return np.stack([clf.probs(p.read_bytes()) for p in percorsi])


def matrice_confusione(vere: np.ndarray, predette: np.ndarray, classi: list[str]) -> None:
    n = len(classi)
    m = np.zeros((n, n), dtype=int)
    for v, p in zip(vere, predette):
        m[v, p] += 1

    largh = max(max(len(c) for c in classi), 8)
    tagli = [c[:7] for c in classi]
    print(f"\n  {'vera \\ predetta':<{largh}} " + " ".join(f"{t:>7}" for t in tagli))
    for i, classe in enumerate(classi):
        riga = " ".join(f"{m[i, j]:>7}" for j in range(n))
        corrette = m[i, i] / max(m[i].sum(), 1)
        print(f"  {classe:<{largh}} {riga}   ({corrette:.0%} corrette)")

    print(f"\n  {'classe':<{largh}} {'precision':>10} {'recall':>8} {'F1':>7} {'n':>6}")
    for i, classe in enumerate(classi):
        tp = m[i, i]
        prec = tp / max(m[:, i].sum(), 1)
        rec = tp / max(m[i].sum(), 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        print(f"  {classe:<{largh}} {prec:>10.1%} {rec:>8.1%} {f1:>7.1%} {m[i].sum():>6}")


def analisi_soglia(probabilita: np.ndarray, vere: np.ndarray,
                   classi: list[str], nome_negativa: str = "normale") -> None:
    """Mostra lo scambio fra copertura e precisione al variare della soglia."""
    predette = probabilita.argmax(axis=1)
    confidenza = probabilita.max(axis=1)

    indice_negativa = classi.index(nome_negativa) if nome_negativa in classi else None
    print(f"\n  {'soglia':>7} {'segnalate':>10} {'copertura':>10} {'corrette':>9}", end="")
    if indice_negativa is not None:
        print(f" {'falsi allarmi':>14}")
    else:
        print()

    for soglia in (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95):
        tiene = confidenza >= soglia
        if indice_negativa is not None:
            # Una segnalazione parte solo se il modello NON dice "normale".
            tiene = tiene & (predette != indice_negativa)
        n = int(tiene.sum())
        if n == 0:
            print(f"  {soglia:>7.2f} {0:>10} {0.0:>9.0%} {'-':>9}")
            continue
        corrette = float((predette[tiene] == vere[tiene]).mean())
        riga = (f"  {soglia:>7.2f} {n:>10} {n / len(vere):>9.0%} "
                f"{corrette:>9.1%}")
        if indice_negativa is not None:
            # Falso allarme: il modello segnala qualcosa su una foto di strada normale.
            falsi = int(((vere == indice_negativa) & tiene).sum())
            riga += f" {falsi:>14}"
        print(riga)

    if indice_negativa is None:
        print(f"\n  (nessuna classe '{nome_negativa}': non si possono misurare i "
              f"falsi allarmi su strada pulita)")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modello", type=Path, default=Path("modello"))
    p.add_argument("--dati", type=Path, default=Path("data_prepared"))
    p.add_argument("--solo-tflite", action="store_true",
                   help="salta la valutazione del modello Keras")
    args = p.parse_args()

    etichette = args.modello / "labels.txt"
    if not etichette.exists():
        print(f"ERRORE: {etichette} non trovato. Esegui prima train.py.")
        return 1
    classi = etichette.read_text(encoding="utf-8").split()

    info_file = args.modello / "training_info.json"
    img_size = json.loads(info_file.read_text(encoding="utf-8")).get("img_size", 224) \
        if info_file.exists() else 224

    print(f"Classi: {', '.join(classi)}   ingresso {img_size}x{img_size}")
    immagini, vere, percorsi = carica_immagini(args.dati / "val", classi, img_size)
    print(f"Validation: {len(immagini)} immagini\n")

    risultati = {}   # nome -> (probabilita, dimensione su disco in KB o None)

    keras_file = args.modello / "modello.keras"
    if not args.solo_tflite and keras_file.exists():
        modello = keras.models.load_model(keras_file)
        risultati["Keras (float32)"] = (
            modello.predict(immagini.astype(np.float32), batch_size=32, verbose=0),
            keras_file.stat().st_size / 1024)

    for nome, file in (("TFLite float32", "modello_float32.tflite"),
                       ("TFLite int8", "modello_int8.tflite")):
        percorso = args.modello / file
        if percorso.exists():
            risultati[nome] = (predici_tflite(percorso, etichette, percorsi),
                               percorso.stat().st_size / 1024)

    if not risultati:
        print("ERRORE: nessun modello da valutare. Esegui train.py e export_tflite.py.")
        return 1

    print("=" * 62)
    print("ACCURATEZZA COMPLESSIVA")
    print("=" * 62)
    for nome, (prob, kb) in risultati.items():
        acc = float((prob.argmax(axis=1) == vere).mean())
        print(f"  {nome:<20} {acc:>7.1%}   {kb:>7.0f} KB")

    if "Keras (float32)" in risultati and "TFLite int8" in risultati:
        delta = ((risultati["TFLite int8"][0].argmax(1) == vere).mean()
                 - (risultati["Keras (float32)"][0].argmax(1) == vere).mean())
        print(f"\n  Costo della quantizzazione int8: {delta * 100:+.1f} punti")
        if delta < -0.05:
            print("  ATTENZIONE: calo oltre 5 punti. Rifai l'export con\n"
                  "  --campioni 1000, o valuta --alpha piu alto nel training.")

    nome_principale = "TFLite int8" if "TFLite int8" in risultati else next(iter(risultati))
    principale = risultati[nome_principale][0]

    print(f"\n{'=' * 62}\nMATRICE DI CONFUSIONE - {nome_principale}\n{'=' * 62}")
    matrice_confusione(vere, principale.argmax(axis=1), classi)

    print(f"\n{'=' * 62}\nSCELTA DELLA SOGLIA - {nome_principale}\n{'=' * 62}")
    print("  Sotto la soglia la UNO Q non apre una segnalazione. Valori per singola\n"
          "  foto: sulla board vision.py chiede in piu la stessa classe in 2 foto su 3\n"
          "  consecutive, quindi i falsi allarmi reali sono meno di quelli qui sotto.")
    analisi_soglia(principale, vere, classi)

    print("\n  Scegli la soglia piu bassa che tiene i falsi allarmi accettabili,\n"
          "  e impostala sulla UNO Q con BUSSENSE_VISION_CONF (default 0.70).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
