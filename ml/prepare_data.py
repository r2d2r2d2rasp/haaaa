"""Prepara il dataset per il training: valida, deduplica, ridimensiona, splitta.

Legge una cartella con un sottodirectory per classe:

    dataset/
      buca/              *.jpg
      cassonetto_pieno/  *.jpg
      rifiuti/           *.jpg
      normale/           *.jpg      <-- classe negativa, vedi README

e scrive immagini RGB JPEG pulite in:

    data_prepared/train/<classe>/...
    data_prepared/val/<classe>/...

Perche non si legge direttamente da dataset/:
  - le immagini raccolte dal web includono file corrotti, PNG con canale alpha,
    JPEG in CMYK e GIF animate, che fanno fallire il decoder di TensorFlow;
  - gli stessi scatti ricompaiono piu volte, ricodificati o ridimensionati.
    Se un doppione finisce meta in train e meta in validation, la validation
    accuracy sale e il modello sembra buono quando non lo e.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageFile, ImageOps

# Molte immagini raccolte dal web hanno l'ultimo blocco JPEG troncato: senza
# questo flag Pillow solleva un errore invece di restituire l'immagine intera.
ImageFile.LOAD_TRUNCATED_IMAGES = True

ESTENSIONI = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tif", ".tiff"}


def dhash(img: Image.Image, lato: int = 16,
          contrasto_minimo: float = 6.0) -> str | None:
    """Impronta percettiva: uguale per lo stesso scatto ricodificato o riscalato.

    Confronta ogni pixel col successivo sulla riga, quindi dipende dalla
    struttura dell'immagine e non dai valori assoluti: resta stabile se
    cambiano luminosita, dimensione o qualita di compressione.

    Restituisce None per le immagini troppo piatte. Ridotta a 16x16 grigi, una
    foto di asfalto uniforme conserva pochissima struttura, e due scatti
    diversi possono produrre la stessa impronta. Siccome e proprio la classe
    'normale' a essere povera di texture, deduplicare alla cieca ne cancellerebbe
    buona parte: meglio tenere qualche doppione che svuotare la classe che
    tiene a bada i falsi allarmi.
    """
    piccola = img.convert("L").resize((lato + 1, lato), Image.Resampling.LANCZOS)
    px = piccola.tobytes()  # mode "L": un byte per pixel, riga per riga

    media = sum(px) / len(px)
    varianza = sum((v - media) ** 2 for v in px) / len(px)
    if varianza ** 0.5 < contrasto_minimo:
        return None

    bit = bytearray()
    for y in range(lato):
        riga = px[y * (lato + 1):(y + 1) * (lato + 1)]
        for x in range(lato):
            bit.append(1 if riga[x] < riga[x + 1] else 0)
    return hashlib.md5(bytes(bit)).hexdigest()


def carica(percorso: Path) -> Image.Image | None:
    """Apre l'immagine come RGB, o None se illeggibile o troppo piccola."""
    try:
        img = Image.open(percorso)
        img.seek(0)  # primo fotogramma delle GIF animate
        # le foto di telefono spesso sono "ruotate" solo nei metadati EXIF
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        return None
    if min(img.size) < 32:
        return None
    return img


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", type=Path, default=Path("../dataset"),
                   help="cartella con un sottodirectory per classe (default: ../dataset)")
    p.add_argument("--out", type=Path, default=Path("data_prepared"),
                   help="cartella di destinazione (default: data_prepared)")
    p.add_argument("--val-split", type=float, default=0.2,
                   help="quota di immagini per la validation (default: 0.2)")
    p.add_argument("--max-side", type=int, default=512,
                   help="lato massimo in pixel delle immagini salvate (default: 512)")
    p.add_argument("--seed", type=int, default=1234,
                   help="seed dello split, per poterlo riprodurre (default: 1234)")
    p.add_argument("--ignora", nargs="*", default=[],
                   help="nomi di sottocartelle da escludere")
    p.add_argument("--no-dedup", action="store_true",
                   help="non rimuovere i doppioni (sconsigliato)")
    args = p.parse_args()

    if not args.dataset.is_dir():
        print(f"ERRORE: cartella dataset non trovata: {args.dataset.resolve()}")
        return 1

    classi = sorted(d.name for d in args.dataset.iterdir()
                    if d.is_dir() and not d.name.startswith((".", "_"))
                    and d.name not in args.ignora)
    if len(classi) < 2:
        print(f"ERRORE: servono almeno 2 classi, trovate {classi}")
        return 1

    print(f"Dataset:  {args.dataset.resolve()}")
    print(f"Classi:   {', '.join(classi)}\n")

    # --- scansione, validazione e deduplica -------------------------------
    # La deduplica e globale fra le classi: se la stessa foto compare in due
    # classi diverse e un errore di etichettatura, e tenerne una sola e
    # comunque meglio che insegnare al modello due risposte opposte.
    visti: dict[str, str] = {}  # impronta -> "classe/nomefile"
    per_classe: dict[str, list[tuple[Path, Image.Image]]] = defaultdict(list)
    n_illeggibili = 0
    n_doppioni = 0
    n_piatte = 0
    conflitti: list[tuple[str, str]] = []

    for classe in classi:
        file = sorted(f for f in (args.dataset / classe).rglob("*")
                      if f.is_file() and f.suffix.lower() in ESTENSIONI)
        for f in file:
            img = carica(f)
            if img is None:
                n_illeggibili += 1
                continue
            if not args.no_dedup:
                impronta = dhash(img)
                if impronta is None:
                    n_piatte += 1  # troppo uniforme per confrontarla, la teniamo
                elif impronta in visti:
                    n_doppioni += 1
                    if visti[impronta].split("/")[0] != classe:
                        conflitti.append((visti[impronta], f"{classe}/{f.name}"))
                    continue
                else:
                    visti[impronta] = f"{classe}/{f.name}"
            per_classe[classe].append((f, img))
        print(f"  {classe:<20} {len(file):>5} file -> {len(per_classe[classe]):>5} usabili")

    print(f"\nScartate: {n_illeggibili} illeggibili, {n_doppioni} doppioni"
          + (f"  ({n_piatte} troppo uniformi per il confronto, tenute)"
             if n_piatte else ""))
    if conflitti:
        print(f"\nATTENZIONE: {len(conflitti)} immagini identiche etichettate "
              f"in classi diverse. Prime 5:")
        for a, b in conflitti[:5]:
            print(f"  {a}  ==  {b}")
        print("  -> controlla l'etichettatura, queste confondono il modello.")

    vuote = [c for c in classi if len(per_classe[c]) < 2]
    if vuote:
        print(f"\nERRORE: classi con meno di 2 immagini usabili: {vuote}")
        return 1

    # --- split stratificato ------------------------------------------------
    if args.out.exists():
        shutil.rmtree(args.out)

    rng = random.Random(args.seed)
    riepilogo: dict[str, dict[str, int]] = {}
    for classe in classi:
        elementi = per_classe[classe]
        rng.shuffle(elementi)
        # almeno 1 immagine in validation e almeno 1 in training
        n_val = max(1, min(len(elementi) - 1, round(len(elementi) * args.val_split)))
        gruppi = {"val": elementi[:n_val], "train": elementi[n_val:]}
        riepilogo[classe] = {s: len(v) for s, v in gruppi.items()}

        for split, elenco in gruppi.items():
            dest = args.out / split / classe
            dest.mkdir(parents=True, exist_ok=True)
            for i, (_origine, img) in enumerate(elenco):
                img.thumbnail((args.max_side, args.max_side), Image.Resampling.LANCZOS)
                img.save(dest / f"{classe}_{i:05d}.jpg", "JPEG", quality=90)

    # --- resoconto ---------------------------------------------------------
    print(f"\nScritto in {args.out.resolve()}\n")
    print(f"  {'classe':<20} {'train':>7} {'val':>7} {'tot':>7}")
    tot_tr = tot_va = 0
    for classe in classi:
        tr, va = riepilogo[classe]["train"], riepilogo[classe]["val"]
        tot_tr, tot_va = tot_tr + tr, tot_va + va
        print(f"  {classe:<20} {tr:>7} {va:>7} {tr + va:>7}")
    print(f"  {'TOTALE':<20} {tot_tr:>7} {tot_va:>7} {tot_tr + tot_va:>7}")

    (args.out / "dataset_info.json").write_text(json.dumps({
        "classi": classi,
        "conteggi": riepilogo,
        "seed": args.seed,
        "val_split": args.val_split,
        "max_side": args.max_side,
        "sorgente": str(args.dataset.resolve()),
        "scartate": {"illeggibili": n_illeggibili, "doppioni": n_doppioni,
                     "troppo_uniformi": n_piatte,
                     "conflitti": len(conflitti)},
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- avvertimenti, prima di sprecare mezzora di training ---------------
    avvisi = []
    if "normale" not in classi:
        avvisi.append(
            "manca la classe 'normale' (asfalto pulito, marciapiede, traffico).\n"
            "    Senza, il modello e costretto a scegliere fra le classi presenti\n"
            "    e segnalera una buca su ogni fotogramma di strada normale.")
    totali = [sum(riepilogo[c].values()) for c in classi]
    if max(totali) > 4 * min(totali):
        avvisi.append(
            f"classi molto sbilanciate ({min(totali)} contro {max(totali)} immagini);\n"
            "    train.py applica i pesi di classe, ma e meglio bilanciare i dati.")
    if tot_tr < 200:
        avvisi.append(f"solo {tot_tr} immagini di training: aspettati un modello fragile.")
    for a in avvisi:
        print(f"\nATTENZIONE: {a}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
