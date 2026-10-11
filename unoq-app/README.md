# BusSense: App per la UNO Q (lato Linux)

Riceve i dati dal telefono (WebSocket, porta 8765) e li salva in `/app/data`:

| Percorso | Contenuto |
|---|---|
| `reports/reports-AAAAMMGG.log` | Una **riga BS1** per segnalazione (GPS + tipo) |
| `journal/obs-AAAAMMGG.jsonl` | Il record completo di ogni segnalazione |
| `events.db` | Segnalazioni (SQLite, WAL) |
| `ts.db` | Traccia GPS a 1 Hz, con IMU e CO2/VOC dal MCU (SQLite, WAL) |
| `media/` | Solo immagini **oscurate** (vuota finché `privacy.redact` non è implementata) |

L'ultima foto ricevuta resta solo in RAM, in `/dev/shm/bussense/latest.jpg`. Serve alla visione e non viene mai scritta su disco.

**Collaudo:** con `BUSSENSE_DEBUG_SAVE_FRAMES=1` ogni foto "frame" viene salvata anche su disco in
`data/debug_frames/` (non oscurata, rotazione automatica agli ultimi ~300 file). Solo per i test:
non lasciarlo attivo sul bus, perché scrive le foto senza oscuramento di volti/targhe.

## Provare sul PC (senza telefono)

```bash
pip install -r python/requirements.txt
```
```bash
cd python && BUSSENSE_DATA=./data python main.py
```
In un secondo terminale:
```bash
python tools/mock/mock_phone.py --url ws://127.0.0.1:8765/phone --seconds 20
```
Atteso:
- 2 eventi confermati (una buca e una frenata);
- il duplicato della buca scartato;
- le righe BS1 in `data/reports/`.

## Sulla UNO Q

**Con App Lab**
1. Crea un'app "BusSense" e copia `python/` dentro la sua cartella `python/`.
2. Verifica che la porta 8765 sia esposta: vedi `app.yaml`, il formato è **da verificare**.
3. I sensori arrivano dallo sketch con `Bridge.notify("cabin_co2", co2, t, rh)` e `Bridge.notify("cabin_voc", sraw, idx)` (PIANO.md §7.2).

**Senza App Lab, per i primi test**
```bash
python3 -m venv ~/bs && ~/bs/bin/pip install -r python/requirements.txt
```
```bash
cd python && BUSSENSE_DATA=~/bussense-data ~/bs/bin/python main.py
```

## Invio a TorinoSegnala (`bussense/cloud.py`)

La UNO Q invia i dati alla piattaforma con le API per i POD ([docs/POD_API.md](../docs/POD_API.md)).
Usa solo la libreria standard di Python, quindi non serve installare altro.
Tutto passa da una coda su disco, `outbox.db`: senza rete o senza chiave i dati restano lì e partono appena possibile.

| Cosa | Endpoint | Quando |
|---|---|---|
| Segnalazioni | `/api/v1/reports` | subito, una alla volta; `pothole`→`buca`, `overflowing_bin`→`cassonetto_pieno`, `bulky_waste`→`rifiuti_abbandonati` |
| Misure del MCU (CO2, T, UR, VOC) | `/api/v1/readings` | campionate ogni `TS_READINGS_S` s, inviate a lotti fino a 100 |
| Battito + posizione | `/api/v1/heartbeat` | ogni `TS_HEARTBEAT_S` s (non va in coda) |

Cosa **non** si invia:
- le frenate e le sterzate (non sono segnalazioni per il Comune);
- le segnalazioni senza posizione o fuori dall'area di Torino accettata dal server (lat 44.9–45.2, lon 7.45–7.9);
- le foto non oscurate: si allega una foto solo se `privacy.redact` l'ha già oscurata.

| Variabile | Default | Note |
|---|---|---|
| `TS_API_KEY` | — | chiave `ts_live_...` dalla Console IT (`/comune/pod`). **Mai nel codice o nel repo** |
| `TS_BASE_URL` | `https://torinosegnala.vercel.app` | |
| `TS_HEARTBEAT_S` / `TS_READINGS_S` | `60` / `60` | |
| `TS_ENABLE` | `1` | `0` = disattiva del tutto l'invio |
| `BUSSENSE_FW` | `bussense-unoq-0.1` | versione mostrata nella Console IT |

Comportamento in caso di errori:
- **401**: chiave errata o revocata. L'app aspetta 5 minuti e riprova.
- **422**: payload rifiutato. La riga viene segnata come `rejected` e non viene più inviata.
- **Rete assente o 5xx**: nuovo tentativo con attesa crescente, fino a 10 minuti.

Comandi utili sulla UNO Q (dalla cartella `python/`):
```bash
python -m bussense.cloud status
```
```bash
TS_API_KEY=ts_live_... python -m bussense.cloud ping
```
`ping` invia un battito: se risponde `{'ok': True}`, il POD risulta collegato nella Console IT.

### Posizione (`bussense/gps.py`)

La posizione per battito, misure e segnalazioni senza fix viene da tre fonti, in quest'ordine:
1. il **telefono**, cioè l'ultimo messaggio `track` se ha meno di 10 s;
2. un **modulo GPS** facoltativo:
   - sul lato Linux (USB/UART, frasi NMEA): `BUSSENSE_GPS_DEV=/dev/ttyUSB0`, con `BUSSENSE_GPS_BAUD` (default 9600);
   - oppure sul MCU: lo sketch chiama `Bridge.notify("gps_fix", lat, lon, hdop, speed_mps, heading_deg)`;
3. una **posizione fissa**: `TS_FIXED_LAT` / `TS_FIXED_LON`, per un POD fermo o per le prove al banco.

Se il modulo GPS non c'è o non ha fix, l'app usa le altre fonti senza errori.

### Prova sul PC senza chiave

```bash
python tools/mock/mock_torinosegnala.py --key ts_live_prova
```
```bash
cd unoq-app/python && BUSSENSE_DATA=./data TS_BASE_URL=http://127.0.0.1:3999 TS_API_KEY=ts_live_prova python main.py
```
Poi avvia `tools/mock/mock_phone.py` come sopra. Il server finto stampa ogni richiesta e applica le stesse
regole di quello vero; con `--fail-every N` risponde 500 a una richiesta ogni N, per provare i nuovi tentativi.

## Dove si aggancia il resto

- **Visione (R2):**
  - imposta `rx.on_frame = funzione(jpeg, meta)`, che riceve le foto già selezionate dal telefono;
  - per ogni rilevamento chiama `rx.report(type=..., src="vision", conf=..., ts_ms=meta["ts_ms"], lat=meta["lat"], ...)`.
- **Privacy:** implementa `bussense/privacy.py`. Finché restituisce `None`, nessuna immagine viene salvata (fail-closed).
