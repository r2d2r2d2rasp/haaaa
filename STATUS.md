# BusSense — Stato del progetto

_Aggiornato al 10 ottobre 2026._

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

## 3. Cose aperte / da tenere a mente

| Punto | Stato |
|---|---|
| IMU | **disattivata**, va riattivata manualmente quando serve (rimuovere i commenti in `CaptureService.kt`) |
| Container `bussense-test` sulla UNO Q | test manuale con Docker, non un deploy App Lab vero |
| `BUSSENSE_DEBUG_SAVE_FRAMES` | **attualmente acceso** sul container di test — da spegnere prima dell'uso reale sul bus |
| URL nell'app del telefono | punta a `ws://10.220.57.130:8765/phone` (indirizzo di questa sessione di test via hotspot) — da aggiornare per la configurazione di rete definitiva del bus |
| GPS | fix ottenuto ma con accuratezza bassa (±44 m) in un test indoor; migliora all'aperto, a cielo libero |

## 4. Prossimi passi possibili

- Riattivare l'IMU quando si vuole tornare al rilevamento di buche/frenate/sbandate
- Impacchettare il server come vera app App Lab (invece del container Docker manuale di test)
- Spegnere `BUSSENSE_DEBUG_SAVE_FRAMES` e ripristinare l'URL di produzione nell'app prima dell'uso
  reale sul bus
- Tarare le soglie IMU (quando riattivata) con un giro registrato, come indicato nel README del
  telefono
- Livello 2/3 del piano (detector LiteRT, oscuramento volti/targhe sul telefono) — non ancora
  iniziati
