"""Fine-tuning di un classificatore di immagini per la UNO Q.

Backbone MobileNetV2 pre-addestrato su ImageNet, testa riaddestrata sulle
classi di BusSense (buca / rifiuti / cassonetto_pieno / normale).

Perche MobileNetV2 e non V3 o EfficientNet: la quantizzazione intera a 8 bit
di MobileNetV3 perde accuratezza, perche hard-swish e i blocchi squeeze-excite
hanno intervalli dinamici che l'int8 rappresenta male. V2 usa solo ReLU6 e
convoluzioni separabili, ed e il caso piu collaudato del convertitore TFLite.
Su Cortex-A53 a 2 GHz un V2 int8 a 224x224 sta sotto i 100 ms, piu che
sufficiente per un bus che scatta una foto ogni pochi secondi.

La normalizzazione sta DENTRO al modello (layer Rescaling): il grafo esportato
accetta pixel 0..255, quindi sulla UNO Q l'unico preprocessing e ritaglio e
resize, gli stessi del training. Un disallineamento di preprocessing fra
training e inferenza e il modo piu comune di ritrovarsi un modello che
"funzionava sul PC" e sbaglia sul campo.

Il training avviene in due fasi:
  1. backbone congelato, si addestra solo la testa (veloce, stabilizza i pesi
     nuovi che partono casuali);
  2. si scongelano gli ultimi blocchi con learning rate basso, per adattare le
     feature di alto livello a buche e rifiuti, che ImageNet non ha mai visto.
Scongelare subito tutto con pesi di testa casuali distruggerebbe le feature
pre-addestrate ai primi gradienti.

Uso:
    python train.py                       # usa data_prepared/
    python train.py --epoche-testa 15 --epoche-finetune 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# Va impostato prima di importare TensorFlow, altrimenti non ha effetto.
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers


def configura_gpu() -> str:
    """Abilita la crescita progressiva della memoria GPU e descrive l'hardware.

    Senza memory growth TensorFlow prealloca quasi tutta la VRAM all'avvio:
    su una scheda da 6 GB questo impedisce di usare il PC per altro durante
    il training, e fa fallire qualsiasi secondo processo TensorFlow.
    """
    gpus = tf.config.list_physical_devices("GPU")
    for g in gpus:
        try:
            tf.config.experimental.set_memory_growth(g, True)
        except RuntimeError:
            pass  # gia inizializzata, non e un problema
    if gpus:
        return f"GPU ({len(gpus)}x)"
    return "CPU (nessuna GPU rilevata: il training sara molto piu lento)"


def costruisci_augmentation() -> keras.Sequential:
    """Augmentation pensata per una fotocamera montata su un autobus.

    I valori sono volutamente contenuti: le foto di strada hanno un alto e un
    basso ben definiti, quindi niente capovolgimenti verticali e rotazioni
    piccole. Il ribaltamento orizzontale invece e lecito (una buca a sinistra
    o a destra resta una buca) e raddoppia di fatto il dataset.
    """
    return keras.Sequential([
        layers.RandomFlip("horizontal"),
        layers.RandomRotation(0.06),                     # ~ +/- 20 gradi
        layers.RandomZoom(0.15, 0.15),                   # distanza variabile
        layers.RandomTranslation(0.1, 0.1),              # inquadratura imprecisa
        layers.RandomBrightness(0.25, value_range=(0, 255)),  # sole, ombra, nuvole
        layers.RandomContrast(0.25),                     # asfalto bagnato o abbagliato
    ], name="augmentation")


def carica_dataset(cartella: Path, img_size: int, batch: int | None, shuffle: bool):
    return keras.utils.image_dataset_from_directory(
        cartella,
        labels="inferred",
        label_mode="categorical",
        image_size=(img_size, img_size),
        batch_size=batch,
        shuffle=shuffle,
        seed=1234,
        interpolation="bilinear",
        # Ritaglio quadrato centrale invece di schiacciare: e quello che fa la board
        # (bussense/classifier.py, preprocess). I frame del telefono sono 16:9, e
        # schiacciati deformerebbero gli oggetti rispetto a queste foto.
        crop_to_aspect_ratio=True,
    )


def scegli_cache(modo: str, n_immagini: int, img_size: int,
                 nome: str) -> str | None:
    """Decide dove tenere le immagini decodificate fra un'epoca e l'altra.

    Rileggere e ridecodificare i JPEG a ogni epoca e lento, soprattutto da
    /mnt/c dentro WSL. Tenerli in RAM e la via piu rapida, ma un'immagine
    224x224 float32 occupa 600 KB: con qualche migliaio di file si arriva a
    diversi GB e il processo viene ucciso a meta training. In quel caso la
    cache va su file, che costa spazio su disco ma non rischia.

    Restituisce il percorso del file di cache, oppure "" per la cache in RAM,
    oppure None per non usarla.
    """
    if modo == "no":
        return None
    if modo == "ram":
        return ""
    byte_stimati = n_immagini * img_size * img_size * 3 * 4
    if modo == "disco" or byte_stimati > 1.5 * 1024 ** 3:
        percorso = Path(tempfile.gettempdir()) / f"bussense_{os.getpid()}_{nome}"
        print(f"Cache {nome} su disco ({byte_stimati / 1024 ** 3:.1f} GB stimati):"
              f" {percorso}")
        return str(percorso)
    return ""


def costruisci_modello(n_classi: int, img_size: int, alpha: float):
    backbone = keras.applications.MobileNetV2(
        input_shape=(img_size, img_size, 3),
        alpha=alpha,
        include_top=False,
        weights="imagenet",
    )
    backbone.trainable = False

    ingresso = keras.Input(shape=(img_size, img_size, 3), name="immagine")
    x = costruisci_augmentation()(ingresso)
    # MobileNetV2 si aspetta valori in [-1, 1]; lo facciamo qui dentro cosi
    # il .tflite esportato accetta direttamente i pixel 0..255.
    x = layers.Rescaling(1.0 / 127.5, offset=-1.0, name="normalizza")(x)
    x = backbone(x, training=False)
    x = layers.GlobalAveragePooling2D(name="pooling")(x)
    x = layers.Dropout(0.3, name="dropout")(x)
    uscita = layers.Dense(n_classi, activation="softmax", name="classe")(x)

    return keras.Model(ingresso, uscita, name="bussense_classificatore"), backbone


def pesi_di_classe(cartella: Path, classi: list[str]):
    """Peso inversamente proporzionale alla frequenza, normalizzato a media 1.

    Serve quando le classi sono sbilanciate: senza, il modello impara che
    rispondere sempre la classe piu numerosa e gia una buona strategia.

    I conteggi si ricavano dai file su disco invece che scorrendo il dataset:
    attraversarlo decodificherebbe ogni JPEG, cioe un'epoca intera sprecata
    prima ancora di cominciare.
    """
    conteggi = np.array([len(list((cartella / c).glob("*.jpg"))) for c in classi],
                        dtype=np.int64)
    pesi = conteggi.sum() / (len(classi) * np.maximum(conteggi, 1))
    return pesi / pesi.mean(), conteggi


def applica_pesi(ds, pesi: np.ndarray):
    """Trasforma (x, y) in (x, y, peso) leggendo il peso dalla classe di y."""
    tabella = tf.constant(pesi, dtype=tf.float32)
    return ds.map(
        lambda x, y: (x, y, tf.gather(tabella, tf.argmax(y, axis=-1))),
        num_parallel_calls=tf.data.AUTOTUNE,
    )


def grafico_storia(storie: list, percorso: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    acc, val_acc, loss, val_loss = [], [], [], []
    for s in storie:
        acc += s.history.get("accuracy", [])
        val_acc += s.history.get("val_accuracy", [])
        loss += s.history.get("loss", [])
        val_loss += s.history.get("val_loss", [])
    confine = len(storie[0].history.get("accuracy", [])) if storie else 0

    fig, assi = plt.subplots(1, 2, figsize=(11, 4))
    for ax, (tr, va, nome) in zip(assi, [(acc, val_acc, "accuratezza"),
                                         (loss, val_loss, "loss")]):
        ax.plot(tr, label="training")
        ax.plot(va, label="validation")
        if confine and len(storie) > 1:
            ax.axvline(confine - 0.5, color="gray", ls="--", lw=1)
            ax.text(confine - 0.4, ax.get_ylim()[0], " fine-tuning",
                    fontsize=8, color="gray", va="bottom")
        ax.set_xlabel("epoca")
        ax.set_title(nome)
        ax.legend()
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(percorso, dpi=110)
    plt.close(fig)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dati", type=Path, default=Path("data_prepared"),
                   help="cartella prodotta da prepare_data.py (default: data_prepared)")
    p.add_argument("--out", type=Path, default=Path("modello"),
                   help="cartella di output (default: modello)")
    p.add_argument("--img-size", type=int, default=224,
                   help="lato dell'immagine in ingresso (default: 224)")
    p.add_argument("--alpha", type=float, default=1.0,
                   help="larghezza di MobileNetV2: 0.35/0.5/0.75/1.0 (default: 1.0). "
                        "Valori bassi = modello piu piccolo e veloce, meno accurato")
    p.add_argument("--batch", type=int, default=32,
                   help="dimensione del batch (default: 32)")
    p.add_argument("--epoche-testa", type=int, default=12,
                   help="epoche con backbone congelato (default: 12)")
    p.add_argument("--epoche-finetune", type=int, default=25,
                   help="epoche di fine-tuning (default: 25, 0 per saltarlo)")
    p.add_argument("--strati-finetune", type=int, default=40,
                   help="quanti strati finali scongelare (default: 40)")
    p.add_argument("--lr-testa", type=float, default=1e-3)
    p.add_argument("--lr-finetune", type=float, default=1e-5,
                   help="deve essere basso, altrimenti cancella le feature "
                        "pre-addestrate (default: 1e-5)")
    p.add_argument("--pazienza", type=int, default=8,
                   help="epoche senza miglioramenti prima di fermarsi (default: 8)")
    p.add_argument("--cache", choices=("auto", "ram", "disco", "no"), default="auto",
                   help="dove tenere le immagini decodificate fra le epoche. "
                        "auto sceglie la RAM sotto 1.5 GB stimati, il disco sopra "
                        "(default: auto)")
    args = p.parse_args()

    dir_train, dir_val = args.dati / "train", args.dati / "val"
    if not dir_train.is_dir() or not dir_val.is_dir():
        print(f"ERRORE: {args.dati}/train o /val non esistono.\n"
              f"Esegui prima:  python prepare_data.py --dataset ../dataset")
        return 1

    print(f"Hardware: {configura_gpu()}")
    print(f"TensorFlow {tf.__version__}\n")

    # Il training si carica non batchato, cosi la cache conserva le singole
    # immagini e lo shuffle puo ricomporre i batch a ogni epoca. Mettendo la
    # cache dopo il batching, invece, ogni epoca rivedrebbe batch identici
    # nello stesso ordine, e lo shuffle diventerebbe inutile.
    ds_train = carica_dataset(dir_train, args.img_size, None, shuffle=True)
    ds_val = carica_dataset(dir_val, args.img_size, args.batch, shuffle=False)
    classi = ds_train.class_names
    n_classi = len(classi)
    print(f"\nClassi ({n_classi}): {', '.join(classi)}")

    pesi, conteggi = pesi_di_classe(dir_train, classi)
    n_train = int(conteggi.sum())
    print("\nBilanciamento del training set:")
    for c, n, w in zip(classi, conteggi, pesi):
        print(f"  {c:<20} {n:>5} immagini   peso {w:.2f}")

    AUTOTUNE = tf.data.AUTOTUNE
    cache_train = scegli_cache(args.cache, n_train, args.img_size, "train")
    cache_val = scegli_cache(args.cache, sum(1 for _ in dir_val.rglob("*.jpg")),
                             args.img_size, "val")

    ds_train_p = ds_train
    if cache_train is not None:
        ds_train_p = ds_train_p.cache(cache_train)
    ds_train_p = (ds_train_p
                  .shuffle(min(n_train, 2048), reshuffle_each_iteration=True)
                  .batch(args.batch))
    ds_train_p = applica_pesi(ds_train_p, pesi).prefetch(AUTOTUNE)

    ds_val_p = ds_val if cache_val is None else ds_val.cache(cache_val)
    ds_val_p = ds_val_p.prefetch(AUTOTUNE)

    modello, backbone = costruisci_modello(n_classi, args.img_size, args.alpha)
    args.out.mkdir(parents=True, exist_ok=True)
    percorso_modello = args.out / "modello.keras"

    def callback_comuni(pazienza: int):
        return [
            keras.callbacks.ModelCheckpoint(
                percorso_modello, monitor="val_accuracy",
                save_best_only=True, mode="max", verbose=0),
            keras.callbacks.EarlyStopping(
                monitor="val_accuracy", patience=pazienza,
                restore_best_weights=True, mode="max", verbose=1),
            keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss", factor=0.5, patience=max(2, pazienza // 3),
                min_lr=1e-7, verbose=1),
        ]

    storie = []

    # --- fase 1: solo la testa --------------------------------------------
    print(f"\n{'=' * 62}\nFASE 1 - testa (backbone congelato)\n{'=' * 62}")
    modello.compile(
        optimizer=keras.optimizers.Adam(args.lr_testa),
        # label_smoothing: le etichette raccolte dal web sono rumorose, e
        # impedire al modello di raggiungere la certezza assoluta lo rende
        # meno sicuro di se sugli errori e piu facile da calibrare a soglia.
        loss=keras.losses.CategoricalCrossentropy(label_smoothing=0.05),
        metrics=["accuracy"],
    )
    storie.append(modello.fit(
        ds_train_p, validation_data=ds_val_p,
        epochs=args.epoche_testa, callbacks=callback_comuni(args.pazienza)))

    # --- fase 2: fine-tuning ----------------------------------------------
    if args.epoche_finetune > 0:
        print(f"\n{'=' * 62}\nFASE 2 - fine-tuning degli ultimi "
              f"{args.strati_finetune} strati\n{'=' * 62}")
        backbone.trainable = True
        for strato in backbone.layers[:-args.strati_finetune]:
            strato.trainable = False
        # I BatchNorm restano congelati: con batch piccoli le statistiche
        # ricalcolate sono rumorose e peggiorano il modello invece di affinarlo.
        n_bn = 0
        for strato in backbone.layers:
            if isinstance(strato, layers.BatchNormalization):
                strato.trainable = False
                n_bn += 1
        addestrabili = sum(1 for s in backbone.layers if s.trainable)
        print(f"Strati del backbone addestrabili: {addestrabili} "
              f"(su {len(backbone.layers)}; {n_bn} BatchNorm congelati)")

        modello.compile(
            optimizer=keras.optimizers.Adam(args.lr_finetune),
            loss=keras.losses.CategoricalCrossentropy(label_smoothing=0.05),
            metrics=["accuracy"],
        )
        storie.append(modello.fit(
            ds_train_p, validation_data=ds_val_p,
            epochs=args.epoche_finetune, callbacks=callback_comuni(args.pazienza)))

    # --- salvataggio -------------------------------------------------------
    modello.save(percorso_modello)
    (args.out / "labels.txt").write_text("\n".join(classi) + "\n", encoding="utf-8")

    perdita, accuratezza = modello.evaluate(ds_val_p, verbose=0)
    (args.out / "training_info.json").write_text(json.dumps({
        "classi": classi,
        "img_size": args.img_size,
        "alpha": args.alpha,
        "backbone": "MobileNetV2",
        "val_accuracy": float(accuratezza),
        "val_loss": float(perdita),
        "immagini_train": int(conteggi.sum()),
        "parametri": int(modello.count_params()),
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    grafico_storia(storie, args.out / "andamento_training.png")

    # tf.data scrive la cache come coppia di file <percorso>.index/.data-*
    for percorso in (cache_train, cache_val):
        if percorso:
            for f in Path(percorso).parent.glob(Path(percorso).name + ".*"):
                f.unlink(missing_ok=True)

    print(f"\n{'=' * 62}")
    print(f"Accuratezza sulla validation: {accuratezza:.1%}  (loss {perdita:.4f})")
    print(f"Modello:  {percorso_modello.resolve()}")
    print(f"Etichette: {(args.out / 'labels.txt').resolve()}")
    print(f"\nProssimo passo:  python export_tflite.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
