# BusSense — Stato del progetto

_Aggiornato all'11 ottobre 2026._

## 1. App Android (telefono) — `phone/android-app`

### IMU disattivata (su richiesta)
In `CaptureService.kt` tutte le chiamate a `ImuProcessor` sono commentate (cercare `// IMU DISATTIVATA`):
creazione/avvio/stop del processore, `onGpsSpeed`, la callback `onImuEvent`, e la riga di stato
"Asse avanti calibrato". Restano attivi **GPS, fotocamera e invio alla UNO Q**.

- Il messaggio `track` continua a portare il blocco `imu` previsto dal contratto, ma con valori a
  zero e `"disabled": true`, così la UNO Q non si rompe.
- `ImuProcessor.kt` è rimasto intatto: per riattivarla basta togliere i commenti in `CaptureService.kt`.

### Toolchain di build sistemata
Il progetto non compilava: Gradle 8.9 / AGP 8.7.3 non supportano il JDK 25 che usa l'Android Studio
installato. Aggiornati:
- Gradle **8.9 → 9.8.1**
- AGP **8.7.3 → 9.4.1** (integra Kotlin nativamente: rimosso il plugin `org.jetbrains.kotlin.android`
  separato, non più necessario/supportato da AGP 9)
- Generato il wrapper Gradle (`gradlew`, `gradlew.bat`, `gradle-wrapper.jar`), che mancava del tutto

APK di debug disponibile in `phone/android-app/BusSense-debug.apk`.

### Collaudo
1. **Emulatore** (Android API 37) contro un server BusSense finto sul PC: GPS, foto, invio,
   riconnessione automatica con backoff — tutto verificato funzionante.
2. **Telefono reale** (Galaxy A26, `SM-A266B`) — APK installato via `adb install`.
3. **Connessione reale con la UNO Q fisica** (non più simulata): vedi punto 2 sotto.

## 2. Server UNO Q (board) — `unoq-app/python`

### Collegamento di rete reale
- Hotspot del telefono attivato (`Galaxy A30s4A5B`)
- UNO Q collegata via Wi-Fi (non USB) alla rete dell'hotspot, tramite `nmcli`
- Telefono e UNO Q sulla stessa subnet (`10.220.57.x` in questa sessione di test)

### Ambiente Python sulla board
Sulla UNO Q non c'erano `pip`/`venv` di sistema funzionanti (niente `ensurepip`, nessun `sudo`
passwordless per installare pacchetti). Soluzione adottata per il test: **Docker** (già presente
sulla board), container `python:3.13-slim` con `websockets` installato al volo, codice del server
montato come volume da `/home/arduino/bussense-test/python`. Il container di test si chiama
**`bussense-test`**.

> ⚠️ Questo è un setup di **test manuale**, non un deploy vero tramite App Lab
> (`arduino-app-cli app new/import`). Per la messa in produzione sul bus andrebbe impacchettato
> come app App Lab vera.

### Collaudo con dati reali (non simulati)
Verificato tramite il server reale in esecuzione sulla UNO Q:
- `hello` dal telefono vero ricevuto correttamente
- Tracce GPS reali (coordinate di Torino), con `ts_src: gnss` (ora dai satelliti)
- Foto reali scattate dalla fotocamera e ricevute
- Tutto persistito correttamente in SQLite (`ts.db`, `events.db`) sulla UNO Q

### Nuova funzione: salvataggio foto di debug
Aggiunta su richiesta, per poter ispezionare le foto "frame" (normalmente tenute solo in RAM per
privacy, mai su disco).

- **`unoq-app/python/bussense/receiver.py`**: nuovo parametro `debug_save_frames` (default `False`)
  sul `Receiver`. Se attivo, ogni foto `frame` viene salvata anche in
  `data/debug_frames/<timestamp>_<device>_<seq>.jpg`, con rotazione automatica (tiene solo le
  ultime ~300, cancella le più vecchie).
- **`unoq-app/python/main.py`**: legge `BUSSENSE_DEBUG_SAVE_FRAMES=1` dall'ambiente e lo passa al
  `Receiver`. Di default `0` → comportamento invariato (solo RAM).
- **`unoq-app/README.md`**: documentato il flag, con avviso esplicito di **non lasciarlo attivo sul
  bus** — le foto salvate così non sono oscurate (niente redazione volti/targhe).
- Testato sulla UNO Q reale: 153 foto scaricate con successo sul PC
  (`C:\Users\marem\Documents\hackturin\debug_frames_pc\`) tramite `adb pull`.

## 3. Visione sulla UNO Q (modello LiteRT) — `ml/`, `unoq-app/python/bussense/`

Al posto del brick Edge Impulse c'è un classificatore addestrato da noi: MobileNetV2 quantizzato
int8 (2,7 MB), eseguito da `bussense/classifier.py` con `ai-edge-litert` sulla CPU della board.
Pipeline di addestramento in `ml/` (vedi `ml/README.md`); si allena su PC con GPU, in WSL2.

- `vision.py` sceglie il motore all'avvio: LiteRT se esiste `python/models/bussense_int8.tflite`,
  altrimenti il brick Edge Impulse. Conferma 2/3, deduplica e invio sono invariati.
- `ml/export_tflite.py --app` installa modello e `labels.txt` in `unoq-app/python/models/`.
- Preprocessing unico (ritaglio quadrato centrale) fra training e board: i frame sono 640x360 e lo
  "Squash" è il problema citato nel PIANO §6.6.
- `requirements.txt` dell'app ora include `ai-edge-litert`, `numpy`, `pillow` (wheel aarch64 fino a
  Python 3.14: il container `python:3.13-slim` va bene).
- `tools/mock/mock_phone.py --frames CARTELLA` manda JPEG veri invece del JPEG finto.

**Collaudo sul PC** (modello addestrato su dati sintetici, solo per provare la catena): telefono finto
→ `main.py` → TorinoSegnala finto. Foto di strada normale: 0 segnalazioni. Foto di buche: 4 segnalazioni
`buca` con `src: vision` accettate (201). Inferenza 5 ms/foto sul PC. **Da misurare sulla board**:
`python -m bussense.classifier foto.jpg --benchmark 50`.

**Modello v2 in uso** (4 classi con `normale`, 195 frame raccolti dalla board): 98,0% sulla validation,
41 ms per foto sulla UNO Q. Nella prova dal vivo, telefono puntato su una stanza: 0 segnalazioni su 178 foto
(la v1 senza `normale` ne aveva fatte 11 in 7 minuti). Documentazione completa in `docs/MODELLO.md`,
grafiche e PDF per la presentazione in `docs/img/presentazione/`.

### Sulla board fisica (11 ottobre)

- Nuova app App Lab **`user:bussense-live`** con il codice di questo repo, **impostata come app di avvio**.
  La vecchia `user:bussense` è intatta (ferma). Container `bussense-live-main-1`.
- **Sketch del MCU** (`unoq-app/sketch/`): è `unoq_registratore.ino` con in più l'invio dei sensori a
  `main.py` via Bridge (`cabin_co2` = CO2eq SGP30 + T/UR AHT20, `cabin_extra` = TVOC + luce) e una pagina
  OLED "BUSSENSE" (telefono, segnalazioni, stato invio). La registrazione col pulsante D2 ora la salva
  `bussense/recorder.py` in `data/registrazioni/`.
- Hardware verificato: AHT20, SGP30 (reagisce), Modulino Movement, luce A0, pulsante D2. OLED presente
  (0x3C) ma non ancora verificato a schermo. Dispositivo sconosciuto su Qwiic 0x7E.
- **Configurazione** in `data/bussense.env` sulla board (App Lab non passa variabili d'ambiente): lì va
  `TS_API_KEY`, **mai nel repo** (è pubblico).
- **Rete**: la board si collega all'hotspot del telefono `Galaxy A30s4A5B` (IP 10.220.57.130), con
  priorità e tentativi infiniti; la Wi-Fi della sede ha l'autoconnessione disattivata
  (`nmcli connection modify "SaleSindacali-WiFi-Ext" connection.autoconnect yes` per riattivarla).
- 11 segnalazioni false della v1 marcate `rejected` nella coda di invio: non partiranno mai.

## 4. Cose aperte / da tenere a mente

| Punto | Stato |
|---|---|
| IMU | **disattivata**, va riattivata manualmente quando serve (rimuovere i commenti in `CaptureService.kt`) |
| Container `bussense-test` sulla UNO Q | test manuale con Docker, non un deploy App Lab vero |
| `BUSSENSE_DEBUG_SAVE_FRAMES` | **attualmente acceso** sul container di test — da spegnere prima dell'uso reale sul bus |
| URL nell'app del telefono | punta a `ws://10.220.57.130:8765/phone` (indirizzo di questa sessione di test via hotspot) — da aggiornare per la configurazione di rete definitiva del bus |
| GPS | fix ottenuto ma con accuratezza bassa (±44 m) in un test indoor; migliora all'aperto, a cielo libero |
| Classe `normale` per la visione | 195 frame di **una sola stanza**: mancano asfalto, marciapiedi e auto visti dal bus. Raccoglierli con `BUSSENSE_DEBUG_SAVE_FRAMES=1` (`dataset/normale/` è in `.gitignore` per privacy) |
| Buche nel dataset | solo 90 contro 600 delle altre classi; integrare con RDD2022 e buche vere dai frame |
| Sensori MCU | collegati via Bridge e verificati. La CO2 dell'SGP30 è *equivalente* (stimata), non misurata come farebbe un SCD41 |

## 5. Prossimi passi possibili

- Riattivare l'IMU quando si vuole tornare al rilevamento di buche/frenate/sbandate
- Impacchettare il server come vera app App Lab (invece del container Docker manuale di test)
- Spegnere `BUSSENSE_DEBUG_SAVE_FRAMES` e ripristinare l'URL di produzione nell'app prima dell'uso
  reale sul bus
- Tarare le soglie IMU (quando riattivata) con un giro registrato, come indicato nel README del
  telefono
- Raccogliere `normale` sulla strada vera e buche dal bus, poi riaddestrare (`ml/README.md`)
- Spegnere `BUSSENSE_DEBUG_SAVE_FRAMES` dopo ogni raccolta (ora è a 0)
- Oscuramento volti/targhe sul telefono — non ancora iniziato
