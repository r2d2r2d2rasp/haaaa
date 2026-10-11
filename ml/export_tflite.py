"""Converte il modello Keras in .tflite quantizzato per la UNO Q.

Produce due file:

  modello_float32.tflite  riferimento non quantizzato, utile per capire quanta
                          accuratezza costa la quantizzazione
  modello_int8.tflite     quello da copiare sulla board: pesi e attivazioni a
                          8 bit interi, circa 4 volte piu piccolo e nettamente
                          piu veloce sulla CPU Cortex-A53 della UNO Q, che non
                          ha unita vettoriale in virgola mobile degna di nota

Quantizzazione intera completa: non basta quantizzare i pesi, servono anche
gli intervalli delle attivazioni. Il convertitore li ricava facendo girare il
modello su un campione di immagini vere (il "representative dataset"): guarda
i valori minimi e massimi che attraversano ogni strato e ne deriva le scale.
Usare rumore casuale al posto di immagini vere darebbe intervalli sbagliati e
un modello int8 che sbaglia molto piu del float.

Ingresso e uscita sono uint8, quindi sulla board si passano i pixel 0..255
grezzi. Le probabilita in uscita vanno riconvertite con la formula
    probabilita = (valore_uint8 - zero_point) * scale
usando i parametri letti dal file .tflite (lo fa unoq-app/python/bussense/classifier.py).

Uso:
    python export_tflite.py
    python export_tflite.py --campioni 500      # calibrazione piu accurata
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from PIL import Image
from tensorflow import keras

# Preprocessing della board (ritaglio centrale + resize): calibrazione e verifica
# devono vedere le immagini esattamente come le vedra la UNO Q.
APP_PYTHON = Path(__file__).resolve().parent.parent / "unoq-app" / "python"
sys.path.insert(0, str(APP_PYTHON))
from bussense.classifier import Classifier, preprocess  # noqa: E402


def modello_per_inferenza(modello: keras.Model) -> keras.Model:
    """Ricostruisce il modello saltando i layer di data augmentation.

    In inferenza RandomFlip e compagnia restituiscono l'input invariato, ma
    restano nel grafo; eliminarli rende la conversione piu prevedibile e il
    file risultante piu piccolo. Funziona perche il modello costruito da
    train.py e una pila lineare di strati.
    """
    saltati = {"augmentation"}
    ingresso = keras.Input(shape=modello.input_shape[1:], name="immagine")
    x = ingresso
    for strato in modello.layers:
        if isinstance(strato, keras.layers.InputLayer) or strato.name in saltati:
            continue
        x = strato(x)
    return keras.Model(ingresso, x, name="bussense_inferenza")


def crea_rappresentativo(cartella: Path, img_size: int, n: int):
    """Generatore di immagini reali per calibrare le scale di quantizzazione.

    Prende immagini da tutte le classi in ordine mescolato: se si calibrasse
    su una sola classe, gli intervalli delle attivazioni sarebbero tarati su
    un sottoinsieme dei casi e le altre classi verrebbero saturate.
    """
    file = sorted(p for p in cartella.rglob("*.jpg"))
    if not file:
        raise SystemExit(f"ERRORE: nessuna immagine in {cartella}")
    rng = np.random.default_rng(1234)
    rng.shuffle(file)
    scelti = file[:n]
    print(f"Calibrazione su {len(scelti)} immagini di {cartella}")

    def generatore():
        for percorso in scelti:
            # stessa scala dell'ingresso del modello: float nell'intervallo 0..255
            img = preprocess(Image.open(percorso), img_size).astype(np.float32)
            yield [img[None]]

    return generatore


def converti(modello: keras.Model, int8: bool, rappresentativo=None) -> bytes:
    conv = tf.lite.TFLiteConverter.from_keras_model(modello)
    if int8:
        conv.optimizations = [tf.lite.Optimize.DEFAULT]
        conv.representative_dataset = rappresentativo
        # Vieta i fallback in virgola mobile: se un operatore non e
        # quantizzabile vogliamo un errore esplicito, non un modello ibrido
        # che sulla board gira a meta velocita senza dirlo.
        conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
        conv.inference_input_type = tf.uint8
        conv.inference_output_type = tf.uint8
    return conv.convert()


def descrivi(percorso: Path) -> dict:
    """Stampa forma e parametri di quantizzazione di ingresso e uscita."""
    interprete = tf.lite.Interpreter(model_path=str(percorso))
    interprete.allocate_tensors()
    ing = interprete.get_input_details()[0]
    usc = interprete.get_output_details()[0]
    print(f"\n  {percorso.name}  ({percorso.stat().st_size / 1024:.0f} KB)")
    for nome, d in (("ingresso", ing), ("uscita", usc)):
        scale, zero = d["quantization"]
        q = f"  scale={scale:.8f} zero_point={zero}" if scale else ""
        print(f"    {nome:<9} {str(d['shape']):<20} {np.dtype(d['dtype']).name}{q}")
    return {"input": ing, "output": usc}


def confronta(percorso_int8: Path, etichette: Path, modello: keras.Model,
              cartella: Path, img_size: int, n: int = 50) -> None:
    """Verifica che il .tflite int8 concordi col modello Keras originale.

    Non e una valutazione di accuratezza (quella la fa evaluate.py): serve a
    intercettare subito una conversione andata storta, in cui il file si
    genera senza errori ma restituisce previsioni scorrelate. Il .tflite gira
    attraverso bussense.classifier, cioe lo stesso codice della UNO Q.
    """
    file = sorted(cartella.rglob("*.jpg"))
    if not file:
        return
    rng = np.random.default_rng(7)
    rng.shuffle(file)
    file = file[:n]

    # Il Keras in un colpo solo: una predict per immagine costringerebbe
    # TensorFlow a ritracciare il grafo a ogni chiamata.
    lotto = np.stack([preprocess(Image.open(f), img_size) for f in file]).astype(np.float32)
    attesi = np.argmax(modello.predict(lotto, batch_size=32, verbose=0), axis=1)

    clf = Classifier(percorso_int8, etichette)
    ottenuti = np.array([int(clf.probs(f.read_bytes()).argmax()) for f in file])

    quota = float((attesi == ottenuti).mean())
    print(f"\nAccordo int8 / Keras su {len(file)} immagini: {quota:.0%}")
    if quota < 0.85:
        print("  ATTENZIONE: scarto elevato. Prova ad aumentare --campioni,\n"
              "  oppure usa modello_float32.tflite se lo scarto resta alto.")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modello", type=Path, default=Path("modello/modello.keras"))
    p.add_argument("--dati", type=Path, default=Path("data_prepared"),
                   help="serve per le immagini di calibrazione (default: data_prepared)")
    p.add_argument("--out", type=Path, default=Path("modello"))
    p.add_argument("--campioni", type=int, default=300,
                   help="immagini usate per calibrare la quantizzazione (default: 300)")
    p.add_argument("--salta-float32", action="store_true")
    p.add_argument("--app", action="store_true",
                   help="copia il modello int8 e labels.txt in unoq-app/python/models/, "
                        "dove li carica bussense/vision.py")
    args = p.parse_args()

    if not args.modello.exists():
        print(f"ERRORE: modello non trovato: {args.modello}\nEsegui prima: python train.py")
        return 1

    modello = keras.models.load_model(args.modello)
    img_size = modello.input_shape[1]
    info = json.loads((args.out / "training_info.json").read_text(encoding="utf-8")) \
        if (args.out / "training_info.json").exists() else {}
    classi = info.get("classi") or \
        (args.out / "labels.txt").read_text(encoding="utf-8").split()
    print(f"Modello: {args.modello}  ({img_size}x{img_size}, {len(classi)} classi)")

    inferenza = modello_per_inferenza(modello)
    args.out.mkdir(parents=True, exist_ok=True)

    if not args.salta_float32:
        f32 = args.out / "modello_float32.tflite"
        f32.write_bytes(converti(inferenza, int8=False))
        descrivi(f32)

    rappresentativo = crea_rappresentativo(args.dati / "train", img_size, args.campioni)
    i8 = args.out / "modello_int8.tflite"
    i8.write_bytes(converti(inferenza, int8=True, rappresentativo=rappresentativo))
    descrivi(i8)

    etichette = args.out / "labels.txt"
    etichette.write_text("\n".join(classi) + "\n", encoding="utf-8")
    confronta(i8, etichette, inferenza, args.dati / "val", img_size)

    if args.app:
        dest = APP_PYTHON / "models"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(i8, dest / "bussense_int8.tflite")
        shutil.copyfile(etichette, dest / "labels.txt")
        print(f"\nInstallato nell'app: {dest / 'bussense_int8.tflite'}")
    else:
        print("\nPer installarlo nell'app della UNO Q:  python export_tflite.py --app")
    print("Prossimo passo:  python evaluate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
