# ml/ — Addestramento del riconoscitore visivo

Documentazione del modello in uso (architettura, risultati, limiti): [`docs/MODELLO.md`](../docs/MODELLO.md).

Fine-tuning di un classificatore di immagini che riconosce **buche**, **rifiuti** e
**cassonetti pieni** nelle foto che il telefono manda alla UNO Q. Il modello viene esportato in
`.tflite` int8 e gira sul lato Linux della board (edge computing, CPU Cortex-A53), dentro
`unoq-app/python/bussense/vision.py`.

```
telefono ──frame 640x360──► UNO Q: vision.py ──► classifier.py (questo modello)
                                       │
                         conferma 2 foto su 3, deduplica 20 m
                                       │
                            rx.report() + sensori MCU (CO2, VOC, T, UR)
                                       │
                            cloud.py ──► TorinoSegnala /api/v1/reports
```

Flusso in quattro comandi, **da WSL** (vedi [Setup](#setup)):

```bash
python prepare_data.py --dataset ../dataset   # pulisce, deduplica, splitta
python train.py                               # fine-tuning su GPU
python export_tflite.py --app                 # -> unoq-app/python/models/bussense_int8.tflite
python evaluate.py                            # accuratezza come sulla board, scelta soglia
```

`--app` copia `bussense_int8.tflite` e `labels.txt` in `unoq-app/python/models/`. Da lì
`vision.py` li carica da solo all'avvio; se il file non c'è, torna al brick Edge Impulse.

---

## Prima di addestrare: i dati

Stato di `dataset/` nel repo:

| Classe | Immagini | Fonte |
|---|---|---|
| `buca` | **90** | keremberke/pothole-segmentation |
| `cassonetto_pieno` | 600 | Garbage_Bin_overflow_images |
| `rifiuti` | 600 | TACO / waste_littering |
| `normale` | **0** | — |

Due problemi, in ordine di gravità.

### 1. Manca `normale`, e senza non si può usare il modello

Un classificatore softmax distribuisce sempre il 100% fra le classi che conosce. Con sole
`buca`, `rifiuti` e `cassonetto_pieno`, una foto di asfalto pulito **deve** finire in una delle
tre: il modello non ha modo di dire "qui non c'è niente". Sul bus, dove quasi ogni foto è strada
normale, questo diventa un flusso continuo di segnalazioni inventate. La conferma 2-su-3 di
`vision.py` attenua i falsi positivi isolati, non quelli sistematici.

La fonte migliore sono i frame veri del telefono sul bus, che la board sa già salvare:

```bash
# sulla UNO Q, solo per la raccolta (STATUS.md: oggi è già acceso nel container di test)
BUSSENSE_DEBUG_SAVE_FRAMES=1   # -> data/debug_frames/, ultimi ~300 frame
```

Fai un giro, scarica i frame (`adb pull`), scarta a mano quelli con buche o rifiuti visibili e
mettili in `dataset/normale/`. Va bene anche un video dal finestrino:

```bash
ffmpeg -i giro_in_bus.mp4 -vf fps=0.5 -q:v 3 ../dataset/normale/giro1_%04d.jpg
```

Quantità: almeno quante le altre classi messe insieme. È lo sfondo statistico del problema.

> **Privacy.** Questi frame non sono oscurati: volti e targhe in chiaro. `dataset/normale/` è in
> `.gitignore` apposta, perché il repo è pubblico. Addestrare in locale va bene, committarli no.

### 2. Le buche sono poche, e vengono da un'altra fotocamera

90 immagini contro 600: `train.py` compensa con i pesi di classe (circa ×3 sulle buche), ma i
pesi non creano esempi che non ci sono. E siccome la buca è la classe dell'MVP, è quella su cui
vale la pena investire. Due mosse:

- **RDD2022** (classe D40, CC BY-SA 4.0, citato nel PIANO): foto stradali da veicolo, molto più
  simili ai nostri frame dei primi piani del dataset attuale.
- **Buche vere di Torino** dai frame del bus: anche poche decine pesano molto, perché sono
  esattamente la distribuzione che il modello vedrà.

Il secondo punto vale per tutte le classi positive. Se i negativi vengono dal bus e i positivi dal
web, il modello può imparare a riconoscere *la fonte* invece del contenuto ("inquadratura da
finestrino = normale"), e sul campo non segnalerebbe più niente. Qualche positivo dal bus in ogni
classe rompe questa scorciatoia.

---

## Setup

Su questo PC l'ambiente è già pronto: Ubuntu in WSL2, venv in `~/venv-ml` con Python 3.12 e
TensorFlow 2.20 con CUDA sulla RTX 4050.

```bash
wsl -d Ubuntu
cd /mnt/c/Users/fedef/Desktop/hackturin/ml
~/venv-ml/bin/python train.py
```

Per ricrearlo altrove:

```bash
wsl --install -d Ubuntu --no-launch
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv --python 3.12 ~/venv-ml
uv pip install --python ~/venv-ml/bin/python -r requirements.txt
```

### Perché WSL e non Windows

Due motivi indipendenti, entrambi bloccanti:

1. **TensorFlow non supporta la GPU su Windows nativo dalla 2.11.** Per CUDA serve WSL2.
2. **Smart App Control** (attivo su questo PC) blocca le DLL non firmate dei wheel pip:
   `ImportError: ... Un criterio di controllo dell'applicazione ha bloccato il file`. Colpisce
   numpy, TensorFlow e `ml_dtypes` in modo imprevedibile. In WSL i binari sono Linux e il problema
   non esiste.

Python 3.12 perché TensorFlow non ha wheel per il 3.14 di Ubuntu 26.04.

---

## I quattro passi

### 1. `prepare_data.py`

Legge `dataset/<classe>/*` e scrive `data_prepared/{train,val}/<classe>/*.jpg`.

- **valida**: scarta file corrotti, applica la rotazione EXIF, converte in RGB;
- **deduplica** con un'impronta percettiva che riconosce lo stesso scatto anche ricodificato o
  ridimensionato. Senza, lo stesso scatto può finire sia in train sia in validation e
  l'accuratezza misurata risulta gonfiata. Le immagini troppo uniformi sono esentate, altrimenti
  la classe `normale` verrebbe decimata;
- **splitta** in modo stratificato e riproducibile (`--seed`).

### 2. `train.py`

MobileNetV2 pre-addestrato su ImageNet, in due fasi: prima solo la testa con il backbone congelato,
poi fine-tuning degli ultimi 40 strati a learning rate basso.

```bash
python train.py                                  # impostazioni predefinite
python train.py --alpha 0.5 --img-size 192       # più veloce sulla board
python train.py --epoche-finetune 40 --strati-finetune 60
```

### 3. `export_tflite.py`

Quantizzazione intera completa, ingresso e uscita `uint8`. La calibrazione usa immagini vere
passate dal preprocessing della board. Verifica anche che l'int8 concordi col Keras originale
(sotto l'85% lo segnala).

### 4. `evaluate.py`

Confronta Keras / TFLite float32 / TFLite int8 sulla validation, stampa la matrice di confusione e
la tabella delle soglie. Le immagini passano da `bussense.classifier.preprocess` e i `.tflite` dalla
classe `Classifier`: **lo stesso codice che gira sulla UNO Q**, quindi i numeri sono quelli della
board, non un'approssimazione.

```
   soglia  segnalate  copertura  corrette  falsi allarmi
     0.50        128        53%     88.3%             14
     0.70         94        39%     94.7%              4
     0.90         61        25%     97.6%              1
```

Alzando la soglia si segnala di meno e si sbaglia di meno. Scegli il valore più basso con falsi
allarmi accettabili e impostalo sulla board con `BUSSENSE_VISION_CONF` (default 0.70). I numeri sono
per singola foto: sulla board si aggiunge la conferma 2-su-3, che li riduce ancora.

---

## Sulla UNO Q

`unoq-app/python/requirements.txt` include già `ai-edge-litert`, `numpy` e `pillow`. Il runtime
LiteRT pesa pochi MB, non serve TensorFlow. I wheel aarch64 coprono Python 3.10–3.14, quindi il
container `python:3.13-slim` usato nei test (STATUS.md) va bene così.

Prova del modello sulla board, dalla cartella `python/`:

```bash
python -m bussense.classifier foto.jpg altra.jpg
python -m bussense.classifier foto.jpg --benchmark 50
```

Il benchmark va lanciato sulla board, non stimato dal PC. Sul PC il modello int8 a 224×224 sta
sotto i 2 ms; i Cortex-A53 sono molto più lenti, ma il budget è largo: il telefono manda una foto
ogni ~4 m, cioè circa 2 al secondo a 30 km/h, e `vision.py` scarta le foto vecchie se
l'inferenza resta indietro. Se fosse troppo lento: `--alpha 0.5`, poi `--img-size 160`.

Variabili d'ambiente lette da `vision.py`:

| Variabile | Default | |
|---|---|---|
| `BUSSENSE_TFLITE` | `python/models/bussense_int8.tflite` | `labels.txt` va nella stessa cartella |
| `BUSSENSE_VISION_CONF` | `0.70` | soglia per foto, da `evaluate.py` |
| `BUSSENSE_VISION_THREADS` | `4` | i 4 core della UNO Q |
| `BUSSENSE_VISION_MODEL` | nome del file | arriva alla piattaforma in `metadata.model` |

### Provare tutta la catena sul PC

```bash
python tools/mock/mock_torinosegnala.py --key ts_live_prova
cd unoq-app/python && BUSSENSE_DATA=./data TS_BASE_URL=http://127.0.0.1:3999 \
    TS_API_KEY=ts_live_prova python main.py
python tools/mock/mock_phone.py --frames cartella_di_jpeg/
```

Con `--frames` il telefono finto manda foto vere invece di un JPEG fittizio: le segnalazioni con
`"src": "vision"` che arrivano al server finto sono passate dal modello.

---

## Scelte tecniche

**Ritaglio quadrato centrale, ovunque.** I frame del telefono sono 640×360. Schiacciati in un
quadrato, buche e cassonetti avrebbero proporzioni diverse dalle foto di addestramento: è il
problema che il PIANO (§6.6) cita, con un 30–40% di accuratezza persa fra "Squash" e "Fit shortest
axis". Training (`crop_to_aspect_ratio=True`), calibrazione, valutazione e board ritagliano tutti
allo stesso modo, con un'unica funzione (`bussense.classifier.preprocess`) fuori dal training. Il
prezzo: i 140 px laterali di ogni lato del frame non vengono guardati. Per le buche, al centro della
carreggiata, conta poco; per i cassonetti sul bordo strada di più. Se diventa un limite, la via è
classificare due ritagli quadrati (sinistro e destro) per frame, non tornare a schiacciare.

**MobileNetV2 e non V3 o EfficientNet.** La quantizzazione int8 di MobileNetV3 perde accuratezza:
hard-swish e i blocchi squeeze-excite hanno intervalli dinamici che gli 8 bit rappresentano male.
V2 usa solo ReLU6 ed è il caso più collaudato del convertitore TFLite.

**Normalizzazione dentro al modello.** Il layer `Rescaling` fa parte del grafo esportato: il
`.tflite` accetta pixel 0–255. Sulla board l'unico preprocessing è ritaglio e resize.

**Classificazione e non detection.** Il PIANO prevedeva un detector Edge Impulse; questo è un
classificatore, come quello che `vision.py` già si aspettava. Un detector darebbe i riquadri ma
richiede annotazioni con bounding box, che il dataset non ha, e per la segnalazione la posizione la
dà il GPS.

**Quantizzazione calibrata su immagini vere.** Con rumore casuale gli intervalli delle
attivazioni sarebbero sbagliati e l'int8 sbaglierebbe molto più del float.

---

## Se il modello va male

| Sintomo | Causa probabile | Rimedio |
|---|---|---|
| Ottimo in validation, pessimo sul bus | positivi dal web e negativi dal bus: il modello riconosce la fonte | aggiungi positivi ripresi dal bus |
| Segnala qualcosa su ogni foto | manca `normale`, o soglia troppo bassa | aggiungi la classe, poi usa la tabella delle soglie |
| Non segnala mai le buche | troppe poche buche, o tutte primi piani | RDD2022 e buche dai frame del bus |
| int8 molto peggio del float | calibrazione insufficiente | `export_tflite.py --campioni 1000` |
| Accuratezza ferma a 1/n classi | learning rate di fine-tuning troppo alto | lascia `--lr-finetune 1e-5` |
| Confonde `rifiuti` e `cassonetto_pieno` | semanticamente vicini | normale; valuta se fonderle |
