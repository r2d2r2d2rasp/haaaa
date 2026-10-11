"""Prepara un dataset di CLASSIFICAZIONE per Edge Impulse: una cartella per etichetta.

Fonti pubbliche (tutte CC BY 4.0, vedi ATTRIBUTION.md generato):
  buca             keremberke/pothole-segmentation          (Roboflow, ~7 MB)
  cassonetto_pieno Akhila-9849/Garbage_Bin_overflow_images  (Roboflow, ~50 MB)
  rifiuti          Akhila-9849/waste_littering              (TACO, ~130 MB)
  normale          LE VOSTRE foto di strade "pulite" (--normale-dir): indispensabili,
                   senza questa classe il modello vede buche e rifiuti ovunque.

Uso:
  pip install huggingface_hub pillow
  python tools/dataset/build_dataset.py --out dataset --normale-dir path/foto_strade --max-per-class 600

Poi su Edge Impulse: Data acquisition -> Upload data -> una cartella alla volta,
"Enter label" = nome della cartella, "Automatically split between training and testing".
"""
import argparse
import io
import random
import zipfile
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download
from PIL import Image, ImageOps

SOURCES = {
    "buca": ("keremberke/pothole-segmentation", "zips"),
    "cassonetto_pieno": ("Akhila-9849/Garbage_Bin_overflow_images", "flat"),
    "rifiuti": ("Akhila-9849/waste_littering", "flat"),
}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def save_resized(data: bytes, dst: Path, max_side: int) -> bool:
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Exception:
        return False
    im.thumbnail((max_side, max_side))
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "JPEG", quality=85)   # ri-salvare toglie anche i metadati EXIF (GPS ecc.)
    return True


def images_from_zips(repo: str, cache: Path) -> list[tuple[str, bytes]]:
    out = []
    for split in ("train", "valid", "test"):
        z = hf_hub_download(repo, f"data/{split}.zip", repo_type="dataset", cache_dir=cache)
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                if Path(n).suffix.lower() in IMG_EXT:
                    out.append((f"{split}_{Path(n).name}", zf.read(n)))
    return out


def images_from_flat(repo: str, cache: Path) -> list[tuple[str, bytes]]:
    d = Path(snapshot_download(repo, repo_type="dataset", cache_dir=cache,
                               allow_patterns=["*.jpg", "*.jpeg", "*.png", "*.webp"]))
    return [(p.name, p.read_bytes()) for p in sorted(d.rglob("*")) if p.suffix.lower() in IMG_EXT]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dataset")
    ap.add_argument("--cache", default="dataset_cache")
    ap.add_argument("--normale-dir", help="cartella con foto vostre di strade senza problemi")
    ap.add_argument("--max-per-class", type=int, default=600)
    ap.add_argument("--max-side", type=int, default=640)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    out, cache = Path(a.out), Path(a.cache)
    rng = random.Random(a.seed)
    counts = {}

    for label, (repo, kind) in SOURCES.items():
        print(f"[{label}] scarico {repo} ...")
        items = images_from_zips(repo, cache) if kind == "zips" else images_from_flat(repo, cache)
        rng.shuffle(items)
        n = 0
        for name, data in items:
            if n >= a.max_per_class:
                break
            if save_resized(data, out / label / f"{label}_{n:04d}.jpg", a.max_side):
                n += 1
        counts[label] = (n, len(items))

    if a.normale_dir:
        files = [p for p in sorted(Path(a.normale_dir).rglob("*")) if p.suffix.lower() in IMG_EXT]
        rng.shuffle(files)
        n = 0
        for p in files[: a.max_per_class]:
            if save_resized(p.read_bytes(), out / "normale" / f"normale_{n:04d}.jpg", a.max_side):
                n += 1
        counts["normale"] = (n, len(files))
    else:
        print("\n!! ATTENZIONE: manca --normale-dir. Serve una classe 'normale' (strade senza problemi),"
              " altrimenti il modello classifica ogni foto come buca/rifiuti.\n")

    (out / "ATTRIBUTION.md").write_text(
        "# Fonti del dataset\n\n"
        "- buca: keremberke/pothole-segmentation (Hugging Face, da Roboflow Universe), CC BY 4.0\n"
        "- cassonetto_pieno: Akhila-9849/Garbage_Bin_overflow_images (da Roboflow Universe, Mariswary Deepak), CC BY 4.0\n"
        "- rifiuti: Akhila-9849/waste_littering (da TACO, Proença & Simões), CC BY 4.0\n"
        "- normale: foto del team BusSense\n", encoding="utf-8")

    print("\nRiepilogo (usate / disponibili):")
    for k, (n, tot) in counts.items():
        print(f"  {k:17s} {n:5d} / {tot}")
    print(f"\nDataset in {out.resolve()}")


if __name__ == "__main__":
    main()
