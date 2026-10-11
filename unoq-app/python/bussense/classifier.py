"""Classificatore LiteRT per le foto "frame" (modello addestrato con ml/ nella radice del repo).

Il modello è un MobileNetV2 quantizzato int8: ingresso uint8 0..255 (la normalizzazione è un
layer dentro al modello), uscita una probabilità per ogni classe di labels.txt.

Gira tutto sulla CPU della UNO Q: serve solo `ai-edge-litert` (pochi MB), non TensorFlow.

Uso a riga di comando (dalla cartella python/):
    python -m bussense.classifier foto.jpg altra.jpg cartella/
    python -m bussense.classifier foto.jpg --benchmark 50      # ms per inferenza sulla board
"""
import argparse
import io
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "models" / "bussense_int8.tflite"


def _interpreter_class():
    """LiteRT è il runtime attuale; tflite_runtime il nome storico; tensorflow solo sul PC."""
    try:
        from ai_edge_litert.interpreter import Interpreter
        return Interpreter
    except ImportError:
        pass
    try:
        from tflite_runtime.interpreter import Interpreter
        return Interpreter
    except ImportError:
        pass
    try:
        import tensorflow as tf
        return tf.lite.Interpreter
    except ImportError:
        raise ImportError("nessun runtime TFLite: pip install ai-edge-litert") from None


def preprocess(img: Image.Image, size: int) -> np.ndarray:
    """Ritaglio quadrato centrale, poi resize a size x size. Restituisce uint8 HxWx3.

    Deve fare la stessa cosa del training (ml/train.py, crop_to_aspect_ratio=True). I frame del
    telefono sono 640x360: schiacciati in un quadrato, buche e cassonetti avrebbero proporzioni
    diverse da quelle viste in addestramento, e un altro team ha perso il 30-40% di accuratezza
    proprio così (PIANO.md 6.6, "Squash" contro "Fit shortest axis"). Il prezzo è perdere i
    bordi laterali del frame.

    ml/evaluate.py usa questa stessa funzione: l'accuratezza che misura è quella della board.
    """
    img = ImageOps.exif_transpose(img).convert("RGB")  # il telefono ruota già i pixel; serve per foto qualsiasi
    w, h = img.size
    s = min(w, h)
    x0, y0 = (w - s) // 2, (h - s) // 2
    img = img.crop((x0, y0, x0 + s, y0 + s)).resize((size, size), Image.Resampling.BILINEAR)
    return np.asarray(img, dtype=np.uint8)


class Classifier:
    """Un interprete LiteRT. Non è thread-safe: va usato da un solo thread (vision lo fa)."""

    def __init__(self, model_path=DEFAULT_MODEL, labels_path=None, threads: int = 4):
        model_path = Path(model_path)
        labels_path = Path(labels_path) if labels_path else model_path.with_name("labels.txt")
        interpreter = _interpreter_class()
        try:
            # 4 thread = i 4 Cortex-A53 della UNO Q
            self.it = interpreter(model_path=str(model_path), num_threads=threads)
        except TypeError:  # runtime vecchi senza num_threads
            self.it = interpreter(model_path=str(model_path))
        self.it.allocate_tensors()
        self.inp = self.it.get_input_details()[0]
        self.out = self.it.get_output_details()[0]
        self.size = int(self.inp["shape"][1])
        self.scale, self.zero = self.out["quantization"]
        self.labels = labels_path.read_text(encoding="utf-8").split()
        if len(self.labels) != int(self.out["shape"][-1]):
            raise ValueError(f"{labels_path.name} ha {len(self.labels)} classi, il modello "
                             f"{int(self.out['shape'][-1])}: file non della stessa esportazione")
        self.model_path = model_path

    def probs(self, image) -> np.ndarray:
        """Probabilità per classe. image: bytes JPEG (come arriva dal telefono), PIL.Image o percorso."""
        if isinstance(image, (bytes, bytearray)):
            image = Image.open(io.BytesIO(image))
        elif not isinstance(image, Image.Image):
            image = Image.open(image)
        x = preprocess(image, self.size)[None]
        if self.inp["dtype"] != np.uint8:
            x = x.astype(self.inp["dtype"])  # modello float32: stessi valori 0..255
        self.it.set_tensor(self.inp["index"], x)
        self.it.invoke()
        y = self.it.get_tensor(self.out["index"])[0].astype(np.float32)
        # uscita quantizzata: intero -> probabilità
        return (y - self.zero) * self.scale if self.scale else y

    def top(self, image) -> tuple[str, float]:
        p = self.probs(image)
        i = int(p.argmax())
        return self.labels[i], float(p[i])


def _cli():
    ap = argparse.ArgumentParser(description="Classifica foto con il modello della visione.")
    ap.add_argument("paths", nargs="+", type=Path, help="immagini o cartelle")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--benchmark", type=int, default=0, help="N inferenze sulla prima immagine")
    a = ap.parse_args()

    clf = Classifier(a.model, threads=a.threads)
    print(f"{clf.model_path.name}: {clf.size}x{clf.size}, classi {', '.join(clf.labels)}, {a.threads} thread")
    files = []
    for p in a.paths:
        files += sorted(f for f in p.rglob("*") if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}) \
            if p.is_dir() else [p]
    if not files:
        sys.exit("nessuna immagine")

    if a.benchmark:
        data = files[0].read_bytes()
        clf.probs(data)  # la prima include l'allocazione
        ms = []
        for _ in range(a.benchmark):
            t0 = time.perf_counter()
            clf.probs(data)
            ms.append((time.perf_counter() - t0) * 1000)
        ms.sort()
        print(f"{a.benchmark} inferenze (decodifica JPEG inclusa): mediana {ms[len(ms) // 2]:.1f} ms, "
              f"min {ms[0]:.1f}, max {ms[-1]:.1f}")
        return

    for f in files:
        t0 = time.perf_counter()
        label, conf = clf.top(f.read_bytes())
        print(f"{f.name:<40} {label:<18} {conf:6.1%}  {(time.perf_counter() - t0) * 1000:6.1f} ms")


if __name__ == "__main__":
    _cli()
