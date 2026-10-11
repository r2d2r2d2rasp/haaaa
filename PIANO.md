# BusSense Torino — Architettura e Piano di Lavoro

*HackTurin · v1 · 10/10/2026.*

Questo piano si basa su una ricerca con verifica delle fonti: datasheet Arduino, sorgenti `app-bricks-py` e `arduino-app-cli`, documentazione Android e Sensirion.

**Come leggere i marcatori:**
- **(da verificare)**: non confermato da fonti primarie. Va provato sull'hardware nella prima ora (sezione 9.2).
- *(stima)*: numero stimato, non misurato.

---

## 0. TL;DR

**Architettura**
- Il **Galaxy A26 5G** fa da *server di sensori*. Espone la fotocamera (snapshot JPEG / MJPEG) e GPS + accelerometro + giroscopio (WebSocket). Fa anche da hotspot e dà internet 5G alla UNO Q.
- **UNO Q, lato Linux** (Python in un'App di App Lab):
  - preleva i dati dal telefono;
  - riconosce i problemi, fonde visione e IMU, toglie i duplicati;
  - oscura volti e targhe;
  - salva la segnalazione con posizione GPS.
- **UNO Q, lato MCU** (STM32): legge i sensori ambientali sul connettore Qwiic e li manda a Linux con il Bridge.

**Collegamento telefono ↔ UNO Q**
- All'hackathon: **hotspot del telefono + UNO Q collegata come client Wi-Fi**. Nessun driver da installare e c'è internet per NTP e aggiornamenti.
- Piano B, utile anche per la configurazione: **cavo** con hub USB-C alimentato + `adb forward`.
- Il tethering USB quasi certamente **non funziona**: il kernel della UNO Q non ha il driver RNDIS.

**Calcolo**
- La UNO Q **non ha NPU**: tutta l'inferenza gira sui 4 core Cortex-A53.
- Budget realistico: **2–5 fotogrammi analizzati al secondo** a 320–416 px.
- Quindi si analizza **un fotogramma ogni ~4 m percorsi**, mai il video continuo.

**MVP (cosa deve funzionare alla demo)**
1. **Buche, frenate brusche e sbandate** dall'IMU del telefono. Sono regole, non serve addestrare niente, e sono il segnale più robusto.
2. **Un solo modello di visione** con 3 classi: `buca`, `cassonetto_traboccante`, `rifiuti_abbandonati`.
3. **Ostacoli in carreggiata** con il modello COCO già installato sulla UNO Q (YOLOX-nano), senza addestramento.
4. **Riga di segnalazione locale** con GPS + tipo, più record JSONL e SQLite.
5. **CO2 vera (SCD41) + indice VOC** letti dal MCU.
6. **Mappa web servita dalla UNO Q** + **modalità replay** di un giro registrato.

**Stretch**
- Lampioni spenti: difficile, servono più notti di confronto.
- Conferma su passaggi ripetuti e stato "risolto".
- Sync su un server.
- Spegnimento controllato col quadro del bus.

**Sensore Seeed "VOC e CO2"**
- È probabilmente il **Grove SGP30**. La sua "eCO2" è **stimata** da idrogeno ed etanolo: **non è CO2**. Inoltre è fuori produzione presso Sensirion.
- Per la CO2 vera aggiungete un **Grove SCD41**.

**I 3 rischi principali**
1. **Stabilità del flusso telefono → UNO Q.** Samsung è il produttore più aggressivo nel chiudere le app in background.
2. **Velocità e precisione dei modelli** sulla CPU della UNO Q, più il calo di qualità tra test web e scheda.
3. **Privacy (GDPR).** Nessuna immagine va salvata senza aver oscurato prima, a bordo, volti e targhe.

---

## 1. Obiettivo e valore

**Il problema.** Buche, rifiuti abbandonati e lampioni guasti oggi si scoprono solo se un cittadino li segnala, oppure con ispezioni costose.

**L'idea**
- Gli autobus percorrono **le stesse strade molte volte al giorno**.
- Un telefono riusato e una UNO Q a bordo trasformano ogni passaggio in un'ispezione gratuita.
- I passaggi ripetuti permettono di **confermare** un problema (visto su più giri) e di capire quando è stato **risolto** (non c'è più). Ne esce un indicatore oggettivo dei tempi di intervento della città.

**Citizen science**
- I cittadini **validano** le segnalazioni da una pagina web. Le loro conferme migliorano il modello.
- I dati sono pubblicati come **open data** (GeoJSON/CSV, CC BY 4.0).
- I telefoni vecchi diventano sensori invece di finire nei rifiuti elettronici.

**Secondo pilastro: l'ambiente.**
- **CO2 in cabina**: misura affollamento e ventilazione, dato utile a GTT.
- Indici VOC/NOx e rumore lungo le linee.

---

## 2. Architettura di sistema

```
 ┌──────────────────── SAMSUNG GALAXY A26 5G ────────────────────┐
 │  Fotocamera ──► app server camera  (snapshot JPEG / MJPEG)    │
 │  GPS + accelerometro + giroscopio ──► SensorServer (WebSocket)│
 │  Hotspot Wi-Fi + 5G (internet per NTP, sync, accesso remoto)  │
 └───────────────▲────────────────────────────▲──────────────────┘
                 │ HTTP (pull, 1–2 foto/s)    │ WebSocket (IMU 50–200 Hz, GPS 1 Hz)
 ┌───────────────┴────────────────────────────┴──────────────────┐
 │ ARDUINO UNO Q — lato LINUX (QRB2210, Debian, App di App Lab)  │
 │  ingest ► campionamento per distanza ► inferenza (CPU)        │
 │  IMU: buche / frenate / sbandate ► fusione + deduplica        │
 │  privacy: oscura volti/targhe ► SQLite + JSONL + riga testo   │
 │  WebUI :7000 (mappa Leaflet, stato, validazione)              │
 └───────────────▲───────────────────────────────────────────────┘
                 │ Bridge (RPC MessagePack, max 256 byte/messaggio)
 ┌───────────────┴───────────────────────────────────────────────┐
 │ ARDUINO UNO Q — lato MCU (STM32U585, sketch Zephyr)           │
 │  Qwiic = Wire1 (3,3 V): SCD41 (CO2) · SGP41/SGP30 (VOC)       │
 │  A0: fonometro (stretch) · in seguito: supervisione alim.     │
 └───────────────────────────────────────────────────────────────┘
                 │ (opzionale, quando c'è rete)
                 ▼
        Server FastAPI + mappa pubblica + validazione cittadini
```

| Componente | Responsabilità | Perché qui |
|---|---|---|
| **Telefono** | Acquisizione: foto, GPS, IMU, livello di rumore. Rete e internet. | Ha sensori migliori della UNO Q (GPS, IMU, fotocamera con OIS) ed è sostituibile. Resta un dispositivo "stupido", con protocolli standard: cambiare telefono è solo una modifica di configurazione. |
| **UNO Q, lato Linux** | Tutta l'elaborazione: riconoscimento, fusione, deduplica, privacy, archivio, mappa locale. | È il "cervello" voluto dal progetto. Funziona offline. Ha 4 GB di RAM e 32 GB di eMMC. |
| **UNO Q, lato MCU** | Sensori I2C, tempi deterministici, in futuro sensore quadro e watchdog di alimentazione. | Il connettore Qwiic e i pin a 3,3 V sono collegati **solo** allo STM32, non a Linux. |
| **Server** (stretch) | Aggregazione tra autobus diversi, mappa pubblica, validazione, open data. | Non serve per la demo: la mappa gira già sulla UNO Q. |

**Note hardware utili**
- La UNO Q ha **solo antenna su PCB**, nessun connettore per antenna esterna. Tenere il telefono vicino, come previsto, e usare un contenitore **non metallico**.
- **Temperatura di esercizio della UNO Q: −10…60 °C ambiente.** Dietro un parabrezza d'estate questo è il vincolo più duro.

---

## 3. Decisioni tecniche chiave

| Decisione | Hackathon (demo) | Autobus reale | Alternative scartate, e perché |
|---|---|---|---|
| **App sul telefono** | App già pronte. **Fotocamera:** *Android IP Camera* (F-Droid, open source; **disattivare TLS** nelle impostazioni) oppure *IP Webcam*. **Sensori:** *SensorServer* (WebSocket; IMU + GPS). | Un'unica **app nativa Kotlin**: foreground service `camera\|location`, impostata come **launcher (Home)** così riparte da sola all'avvio. | **Arduino IoT Remote:** si ferma quando lo schermo si spegne, richiede un account, il codice scade in 5 minuti. Va bene solo per un primo test veloce. **Pagina nel browser:** serve HTTPS e si blocca a schermo spento. |
| **Rete** | **Hotspot del telefono**, UNO Q client (`nmcli`). Il telefono è il gateway: `ip route`. | **UNO Q come access point** se `iw list` mostra la modalità AP **(da verificare)**. Così la rete torna su da sola dopo un riavvio, mentre Android non riattiva l'hotspot dopo un reboot. In alternativa, cavo con hub + `adb forward`. | **Tethering USB:** il kernel della UNO Q ha `cdc_ncm` ma non `rndis_host`, e Android usa RNDIS di default. Va anche riattivato a mano dopo ogni riavvio del telefono. |
| **Chi chiama chi** | **Pull:** è la UNO Q a collegarsi ai server sul telefono. | Uguale. | **Push dal telefono:** se il Wi-Fi non ha internet, Android instrada il traffico sul 5G e i dati non arrivano. |
| **Software UNO Q** | Un'**App di App Lab** (`app.yaml` + `python/` + `sketch/`) con "Run at startup". | Stessa App. Valutare `systemd` più watchdog se App Lab si dimostra fragile. | Python "a mano" fuori da App Lab: il Bridge col MCU è meno comodo. |
| **Inferenza** | **Edge Impulse** (`.eim`) con i Brick di App Lab: YOLOX-nano COCO già installato, più un modello custom (YOLO-Pro nano o FOMO). | Uguale. Opzionale: pre-filtro sul telefono quando ci sarà l'app nativa. | **Ultralytics YOLO11n/26n** (NCNN): più controllo, ma licenza **AGPL anche sui pesi**, e per uso embedded non aperto serve la licenza Enterprise. Va bene solo se tutto il progetto è open source. |
| **Archivio** | `sqlite3` della libreria standard, in modalità WAL, + giornale JSONL + riga testo, tutto in `/app/data`. | Uguale, più rotazione e quote. | **Brick SQLStore:** fa un commit per ogni riga e non usa WAL. **Brick TimeSeriesStore** (InfluxDB): **cancella i dati dopo 7 giorni** per default. Usarlo solo per un grafico live, impostando `retention_days`. |
| **Orario** | **Ora UTC del GPS del telefono** come riferimento; NTP via hotspot. Ogni record porta `ts_src`. | Uguale + batteria tampone sull'RTC (pin VCOIN, tramite Media Carrier) **(da verificare)**. | Orologio della UNO Q: **non ha batteria per l'RTC**, quindi dopo un'interruzione di corrente l'ora riparte sbagliata. |
| **Sensori ambientali** | Sul **MCU** via **Qwiic = `Wire1`** (non `Wire`!), poi `Bridge.notify` ogni 1–5 s. | Uguale, più un modulo esterno per l'aria esterna (SEN66) su un bus I2C separato. | Leggerli da Linux: impossibile, Linux non vede il Qwiic. Fallback: adattatore USB-I2C (Sensirion SensorBridge). |
| **Mappa** | Brick **WebUI** sulla UNO Q (porta 7000) + Leaflet. Funziona offline, con tile già in cache. | WebUI locale + server pubblico. | Server cloud per la demo: dipenderebbe dal Wi-Fi della sede. |

**Se in futuro si passa a un telefono più vecchio**
- Il giroscopio potrebbe mancare: si rilevano le buche con il solo accelerometro.
- Potrebbe esserci solo Wi-Fi a 2,4 GHz: usare i canali 1, 6 o 11.
- Il pre-filtro sul telefono non sarà possibile: la pipeline deve funzionare **anche solo sulla UNO Q**. È già progettata così.

---

## 4. Pipeline dati end-to-end

| # | Passo | Dove | Frequenza / budget |
|---|---|---|---|
| 1 | GPS (lat, lon, accuratezza, velocità, direzione, ora UTC) | Telefono → WS | 1 Hz |
| 2 | Accelerometro + giroscopio | Telefono → WS | 50–200 Hz (Android limita a 200 Hz senza permesso speciale) |
| 3 | **Campionamento per distanza:** si chiede uno snapshot ogni ~4 m percorsi, con velocità > 0,5 m/s. Fermi alle fermate: niente foto (privacy + duplicati). | UNO Q | ~1–2 foto/s a 30 km/h |
| 4 | Inferenza sul fotogramma, ritagliando la metà bassa per la strada | UNO Q CPU | 100–300 ms/foto *(stima)* |
| 5 | Regole IMU: buche, frenate brusche, sbandate. Un buffer circolare di 2–3 s di foto permette di associare all'evento IMU la foto di 1–2 s prima. | UNO Q | continuo |
| 6 | Fusione + deduplica nello stesso passaggio: stesso tipo entro 5–10 m e 3 s = un'unica osservazione; si tiene la foto migliore. | UNO Q | per evento |
| 7 | **Privacy:** oscuramento pieno di volti e targhe sul ritaglio. Se l'oscuratore fallisce si salvano **solo i metadati**. | UNO Q | per evento |
| 8 | Salvataggio: riga testo + JSONL + SQLite (WAL); ritaglio JPEG ≤ 384 px | UNO Q eMMC | ~1 evento ogni 10 s |
| 9 | Serie temporale 1 Hz: traccia GPS + CO2/VOC/rumore + indicatori IMU, salvata a blocchi ogni 10 s | UNO Q | 1 Hz |
| 10 | Aggregazione tra passaggi: candidata → confermata → risolta | UNO Q (poi server) | ogni ~5 min |
| 11 | Mappa locale (WebUI) e, se c'è rete, sync idempotente verso il server | UNO Q → server | ogni 60 s |

**Divisione dei core (indicativa):**

| Core | Compito |
|---|---|
| 1 | Detector |
| 2 | IMU, GPS, ingest |
| 3 | I/O, database, WebUI |
| 4 | Libero (temperatura) |

Sopra i ~70 °C del SoC si riduce la frequenza di analisi.

---

## 5. Formato dati

### 5.1 Tipi di evento (schema v1)

| Codice | Etichetta IT | Tipo | Fonte | Fase |
|---|---|---|---|---|
| `pothole` | Buca | puntuale | visione, IMU, fusione | **MVP** |
| `overflowing_bin` | Cassonetto traboccante | puntuale | visione (giorno) | **MVP** |
| `bulky_waste` | Rifiuti/ingombranti abbandonati | puntuale | visione (giorno) | **MVP** |
| `road_obstacle` | Ostacolo in carreggiata | puntuale | visione (COCO) | **MVP** (solo interno, poi validato) |
| `harsh_braking` | Frenata brusca | hotspot aggregato | IMU + GPS | **MVP** (pubblico solo come hotspot) |
| `swerve` | Sbandata / scarto laterale | hotspot aggregato | IMU | **MVP** |
| `roughness` | Irregolarità del manto | indice per tratto | IMU | **MVP** |
| `litter` | Rifiuti dispersi | indice per tratto | visione | stretch |
| `streetlight_out` | Lampione spento | puntuale | luce/visione (notte) | stretch |
| `streetlight_day_on` | Lampione acceso di giorno | puntuale | visione (giorno) | stretch |
| `graffiti`, `sign_damage`, `faded_marking` | Graffiti, cartello danneggiato, strisce sbiadite | puntuale | visione | futuro |
| `incident_candidate` | (interno) possibile incidente | puntuale | IMU + visione | stretch, **mai pubblico, nessuna immagine** |

**Esclusi per scelta etica:** persone, assembramenti, "comportamenti sospetti", sosta irregolare e singoli veicoli o targhe. Il sistema guarda **infrastrutture, non persone**.

### 5.2 La riga di segnalazione locale (quella richiesta)

Una riga per evento, campi separati da `;`, scritta in append con `fsync` in `/app/data/reports/reports-AAAAMMGG.log`:

```
BS1;2026-10-10T14:23:51.284Z;gnss;45.070512;7.686931;4.8;6.2;87;pothole;fusion;0.81;2;urban-v0.3;unoq-01;0192f3a1-7c2e-7b4d-9e1f-5d20c4f8a6e1
```

| # | Campo | Significato |
|---|---|---|
| 1 | `BS1` | Versione del formato |
| 2 | `ts_utc` | Ora dell'evento (ISO 8601, UTC) |
| 3 | `ts_src` | Fonte dell'ora: `gnss` \| `ntp` \| `unsynced` |
| 4–5 | `lat;lon` | Posizione **stimata dell'oggetto**, non del bus |
| 6 | `acc_m` | Accuratezza GPS in metri |
| 7 | `speed_mps` | Velocità del bus |
| 8 | `heading` | Direzione del bus in gradi |
| 9 | `type` | Tipo di evento (codice della tabella 5.1) |
| 10 | `src` | Fonte: `vision` \| `imu` \| `fusion` \| `env` |
| 11 | `conf` | Confidenza, 0–1 |
| 12 | `severity` | Gravità, 1–3 |
| 13 | `model` | Versione del modello |
| 14 | `device_id` | Identificativo del dispositivo |
| 15 | `event_id` | UUIDv7 |

### 5.3 Record completo (JSONL, una riga per osservazione)

```json
{"schema":"bs.obs.v1","id":"0192f3a1-7c2e-7b4d-9e1f-5d20c4f8a6e1","seq":18342,"device_id":"unoq-01",
 "ts":"2026-10-10T14:23:51.284Z","ts_src":"gnss","mono_ns":5123456789012,
 "obs":{"lat":45.070490,"lon":7.686820,"acc_m":4.8,"speed_mps":6.2,"heading_deg":87.0,"fix_age_ms":320},
 "tgt":{"lat":45.070512,"lon":7.686931,"dist_m":9.5,"side":"right"},
 "type":"pothole","severity":2,"src":"fusion","conf":0.81,"model":"urban-v0.3","n_frames":4,
 "imu":{"zdiff_ms2":7.9,"speed_bin":"20-30"},
 "media":{"path":"media/2026-10-10/9f2c….jpg","sha256":"9f2c…","redacted":true,"faces":0,"plates":1},
 "env":{"co2_ppm":812,"voc_idx":143,"t_c":24.1,"rh_pct":48},
 "ctx":{"light":"day","sun_elev_deg":31.2,"line":null}}
```

**Regole**
- Le osservazioni con `acc_m > 15` m o con un fix più vecchio di 2 s non vanno in mappa.
- Sotto i portici l'errore GPS cresce: il GPS dell'A26 è a banda singola L1, con 3–10 m di errore nei canyon urbani.
- `id` è un UUIDv7, ordinato nel tempo: rende la sync idempotente.
- `seq` è un contatore locale che fa da cursore di sync.

### 5.4 SQLite (sulla UNO Q)

```sql
-- /app/data/events.db
PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
CREATE TABLE IF NOT EXISTS observation(
  id TEXT PRIMARY KEY, seq INTEGER UNIQUE NOT NULL, device_id TEXT NOT NULL,
  ts_utc TEXT NOT NULL, ts_src TEXT NOT NULL CHECK(ts_src IN('gnss','ntp','unsynced')), mono_ns INTEGER,
  obs_lat REAL, obs_lon REAL, acc_m REAL, speed_mps REAL, heading_deg REAL,
  tgt_lat REAL NOT NULL, tgt_lon REAL NOT NULL,
  type TEXT NOT NULL, src TEXT NOT NULL, conf REAL NOT NULL CHECK(conf BETWEEN 0 AND 1),
  severity INTEGER, model TEXT, media_sha256 TEXT, env_json TEXT, issue_id TEXT
);
CREATE TABLE IF NOT EXISTS media(
  sha256 TEXT PRIMARY KEY, path TEXT NOT NULL,
  redacted INTEGER NOT NULL CHECK(redacted = 1),   -- impossibile indicizzare un'immagine non oscurata
  created_at TEXT NOT NULL, synced_at TEXT
);
CREATE TABLE IF NOT EXISTS issue(                   -- aggregato su più passaggi
  id TEXT PRIMARY KEY, type TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN('candidate','confirmed','resolved','dismissed','expired')),
  lat REAL NOT NULL, lon REAL NOT NULL, alpha REAL DEFAULT 1, beta REAL DEFAULT 1,
  n_hits INTEGER DEFAULT 0, n_passes INTEGER DEFAULT 0, consec_miss INTEGER DEFAULT 0,
  first_seen TEXT, last_seen TEXT, resolved_at TEXT, human_label TEXT
);
```

### 5.5 Serie temporale continua (`/app/data/ts.db`, WAL, `synchronous=NORMAL`, commit ogni 10 s)

```
t_utc, lat, lon, acc_m, speed_mps, heading_deg, cam_on,
co2_ppm, voc_idx, nox_idx, t_c, rh_pct, noise_laeq_db, az_rms_ms2, rough_idx, decel_max_ms2, latacc_max_ms2, flags
```

**`flags`** è una maschera di bit:

| Bit | Significato |
|---|---|
| 1 | GPS scarso |
| 2 | Fermo |
| 4 | Sensore in riscaldamento |
| 8 | Valore vecchio |
| 16 | Zona privacy / deposito |
| 32 | Ora non sincronizzata |

**Rumore**
- Si salvano solo `LAeq,1s` e `LAmax`.
- La media su 10 s si calcola come media **energetica**: `10·log10(mean(10^(L/10)))`.

### 5.6 Cartelle sulla UNO Q e conservazione

L'App gira in un container. `/app/data` corrisponde a `~/ArduinoApps/<app>/data` sull'host.

```
/app/data/
├── reports/reports-AAAAMMGG.log     # la riga BS1 (5.2)
├── journal/obs-AAAAMMGG.jsonl       # record completi (5.3), ruotati e compressi
├── events.db  ts.db                 # SQLite
└── media/AAAA-MM-GG/<sha256>.jpg    # SOLO ritagli oscurati, lato max 384 px, JPEG q80, senza EXIF
```

| Dato | Conservazione |
|---|---|
| Fotogrammi e audio grezzi | **Solo in RAM** (`/dev/shm`), meno di 2 s, mai su disco |
| Ritagli oscurati | Quota di 8 GB a buffer circolare; cancellati 14 giorni dopo la sync |
| Traccia 1 Hz | 30 giorni |
| Metadati delle osservazioni | Fino alla conferma di ricezione dal server + 90 giorni |

**Scrittura dei media:** file temporaneo → `fsync` → `rename` → riga nel DB. Se salta la corrente resta al massimo un file orfano, mai un record rotto.

---

## 6. Rilevamento per categoria

### 6.1 Buche (MVP, due metodi che si confermano a vicenda)

**IMU (senza addestramento)**
1. **Riorientare** gli assi del telefono su quelli del bus:
   - verticale = gravità (filtro passa-basso);
   - avanti = direzione delle accelerazioni quando la velocità GPS cambia;
   - laterale = prodotto vettoriale dei due.
   - Il supporto è fisso, quindi si calibra una volta sola.
2. Filtro passa-banda **1–20 Hz** sull'asse verticale.
3. Indicatori: picco, **Z-DIFF**, deviazione standard su 0,5 s, picco della velocità di beccheggio dal giroscopio.
4. **Normalizzare per velocità.** Sotto i 10 km/h si ignora. Soglie per fascia (10–20, 20–30, 30–40, >40 km/h), al 99,5° percentile.
5. **Maschere contro i falsi positivi:** binari del tram, dossi e rallentatori (da OSM), pavé.
6. Stretch: il **doppio colpo asse anteriore → posteriore**, distanziato di Δt = passo ÷ velocità (circa 0,7 s a 30 km/h con un passo di ~6 m: misuratelo sul vostro bus).

Le sospensioni pneumatiche del bus smorzano le buche piccole. In compenso le linee ripetute danno una base di confronto per ogni tratto. Pothole Patrol (MIT) confermava una buca solo se vista in ≥ 4 passaggi.

**Visione**
- Detector sulla metà bassa del fotogramma, a 1–2 fps.
- Dataset:
  - **RDD2022**, classe D40 = buca; sottoinsiemi Giappone, India e Repubblica Ceca; licenza CC BY-SA 4.0.
  - 200–500 fotogrammi di Torino etichettati da voi: la camera del bus è alta 2,5–3 m e ci sono pavé e binari.
- Qualità attesa a 320 px: F1 ≈ 0,5–0,65 *(stima)*.
- **Fusione:** l'IMU scatta → si aggancia la foto di 1–2 s prima → la visione conferma.

### 6.2 Rifiuti (MVP: cassonetti traboccanti e ingombranti)

- Dal bus a 1–2 fps i rifiuti piccoli si vedono male (recall bassa). Si puntano gli **oggetti grandi**: cassonetti, cassonetti traboccanti, mucchi di rifiuti, ingombranti.
- I rifiuti dispersi diventano solo un **indice di densità per tratto**.
- Dataset:
  - **GBS – Garbage Bin Status** (Zenodo; 16.857 immagini; classi garbage / garbage_bin / overflow; CC BY 4.0) + ~300 fotogrammi di Torino.
  - TACO è fatto di foto ravvicinate: poco adatto alla vista dal bus.
- Etichettatura rapida: **autodistill** (Grounding DINO) sul laptop, poi revisione manuale di 300–500 fotogrammi.

### 6.3 Lampioni spenti (stretch, da dire onestamente: è difficile)

- **Non esiste un inventario pubblico** dei lampioni di Torino:
  - il portale open data non ha dataset sull'illuminazione;
  - OSM ha solo ~705 nodi `highway=street_lamp` in città.
- Il progetto deve quindi **costruirsi la propria mappa dei lampioni**, che è già di per sé un risultato di citizen science.
- **Metodo consigliato**
  - Un **sensore di luce rivolto verso l'alto** sul Qwiic (VEML7700 o TSL2591), letto solo di notte (sole sotto −6°).
  - I lampioni appaiono come picchi periodici ogni 20–40 m.
  - Un picco che manca rispetto alle notti precedenti è un candidato guasto; lo si conferma dopo ≥ 3 notti.
  - Il sensore di luce del telefono **non serve dentro il bus**.
- **Alternativa:** cercare macchie luminose nella parte alta del fotogramma, con **esposizione bloccata**. Questo richiede l'app nativa.
- **Canale reale per le segnalazioni:** Iren Smart Solutions, app "Luce in Città". Ogni palo ha un codice.

### 6.4 Incidenti e pericoli (realistico: quasi-incidenti)

- **Frenate brusche e sbandate del bus** (MVP, il segnale più economico e utile). Mappa dei **"quasi-incidenti"**. Soglie iniziali, da tarare:

  | Evento | Soglia |
  |---|---|
  | Rischio per i passeggeri in piedi | decelerazione ≥ 1,5 m/s² |
  | Quasi-incidente | ≥ 2,5 m/s² per ≥ 0,5 s |
  | Grave | ≥ 3,5 m/s² |
  | Sbandata | laterale ≥ 2 m/s² sopra i 15 km/h |

  - Raggruppamento tra giorni diversi: DBSCAN, raggio 25–30 m, almeno 3 eventi.
  - **Normalizzare per passaggi** (eventi per passaggio del bus), non contare gli eventi grezzi.
- **Ostacolo in carreggiata** (MVP): YOLOX-nano COCO già presente sulla UNO Q. Un veicolo o una persona fermi nella corsia per N fotogrammi mentre il bus si muove generano l'evento. Nessun addestramento.
- **"Incidente" come classe visiva:** non affidabile su un singolo fotogramma.
  - Resta `incident_candidate`, interno, senza immagine, con revisione umana.
  - Il sistema **non** è un servizio di emergenza: nessuna chiamata automatica al 112.

### 6.5 Altri fattori utili (soprattutto stretch)

- **Congestione** (MVP, a costo quasi zero): velocità del bus per tratto, escludendo le soste alle fermate. Le fermate si prendono dal **GTFS di GTT** (CC BY 4.0, controllare le date di validità del feed).
- **Rugosità stradale** (MVP): RMS dell'accelerazione verticale filtrata, per tratto di 20–50 m, normalizzata per velocità, mediana tra i passaggi.
- **Rumore** (stretch): fonometro dedicato oppure microfono del telefono. Il microfono dà solo trend relativi. **Mai registrare audio.**
- **Futuro:** strisce pedonali sbiadite, graffiti, segnali danneggiati, acqua stagnante.

### 6.6 Modelli: catena consigliata

| Funzione | Modello | Runtime | Frequenza |
|---|---|---|---|
| Ostacoli (veicoli, persone) | YOLOX-nano 416 COCO **già presente** | EI `.eim` (Brick) | 1–2 fps |
| Buca + cassonetto traboccante + rifiuti | **Un unico detector a 3 classi**: YOLO-Pro nano 320 su Edge Impulse (licenza pulita, si integra in App Lab) | EI `.eim` | 1–2 fps, area strada |
| Buche IMU, rugosità, frenate | Regole (numpy/scipy) | Python | 50–200 Hz |
| Opzionale | VLM in cloud (brick `cloud_llm`, es. Claude Haiku 5.5, pensiero basso) **solo** su fotogrammi candidati, come seconda opinione | HTTPS | stretch |

**Insidie note**
- **Resize:** un team ha perso il 30–40% di accuratezza tra il test web di Edge Impulse e la UNO Q. Il resize "Squash" non corrispondeva a quello reale; con **"Fit shortest axis"** si è risolto quasi tutto. Il pre-processing sulla scheda deve essere identico a quello dell'impulso.
- **Variabile del modello custom:** il Brick video legge `EI_V_OBJ_DETECTION_MODEL`.
- **Senza camera USB/CSI** l'App **non parte** ("no camera device found"). Bisogna dichiarare nell'`app.yaml`, sotto il brick, `devices: [remote_camera_0]`.
- **Model card pubbliche** con mAP 0,99 non sono validate: non fidatevi.

---

## 7. Sensori ambientali

### 7.1 Cosa comprare

| Livello | Contenuto | ~€ |
|---|---|---|
| **Minimo** (per l'hackathon) | Grove **SCD41** (CO2 vera, 0x62) + Grove **SGP41** (indici VOC + NOx, 0x59) oppure l'SGP30 che avete già (solo VOC relativo) + 2 cavi Qwiic↔Grove (SparkFun PRT-15109) + hub I2C Grove | 75–95 |
| **Consigliato** | Minimo + **SEN66** per l'aria esterna (PM1–10, T, RH, VOC, NOx, CO2; 0x6B, alimentazione 3,3 V esterna) + SHT40 + fonometro DFRobot SEN0232 (analogico, su A0) + sensore di luce VEML7700 (lampioni) + scatola IP65 e schermo anti-sole | 220–280 |
| **Ideale** | Consigliato + seconda unità identica (confronto incrociato) + SCD30 di controllo + co-locazione di 2 settimane con una stazione ARPA | 450–700 |

**Da evitare per affermazioni scientifiche:** Grove Multichannel Gas v2 (solo qualitativo) e la "eCO2" dell'SGP30.

### 7.2 Collegamenti

```
UNO Q MCU (sketch Zephyr)
 ├─ Wire1 = Qwiic (I2C4, 3,3 V) → hub Grove → SCD41 0x62 + SGP41 0x59 [+ SGP30 0x58]   ← in cabina
 ├─ Wire  = D20/D21 (I2C2) → (stretch) SEN66 0x6B + SHT40 0x44, modulo esterno
 ├─ A0    → SEN0232 rumore (0,6–2,6 V), campionato ≥ 8 Hz → LAeq 1 s calcolato sul MCU
 └─ Bridge.notify(...) ogni 1 s (VOC/NOx) e 5 s (CO2) → Python su Linux aggiunge ora + GPS
```

**Regole**
- **Moduli Grove alimentati a 3,3 V.** Mai 5 V su D3 o su A0–A5.
- **Conflitti di indirizzo:** SGP40 e SGP41 (0x59); SHT40 e Modulino Thermo (0x44).
- **L'SCD41 assorbe picchi fino a ~205 mA a 3,3 V.** Il datasheet della UNO Q non indica un limite di corrente sul Qwiic: non metteteci altri carichi pesanti.
- **La libreria HM3301 usa `Wire` fisso:** sulla UNO Q va su D20/D21, oppure va modificata.
- **Le librerie Sensirion su `arduino:zephyr` non sono ancora confermate** da nessun report funzionante. Compilatele nella prima ora.
  - Fallback: Sensirion SEK-SensorBridge via USB, letto da Linux con `sensirion-shdlc-sensorbridge`.

`sketch/sketch.yaml` (librerie):

```yaml
profiles:
  default:
    platforms:
      - platform: arduino:zephyr
    libraries:
      - Sensirion Core (0.7.3)
      - Sensirion I2C SCD4x (1.1.0)
      - Sensirion I2C SGP41 (1.0.0)
      - Sensirion Gas Index Algorithm (3.2.3)
```

Scheletro dello sketch. È uno schema, non è stato compilato:

```cpp
#include <Arduino_RouterBridge.h>
#include <SensirionI2cScd4x.h>
#include <SensirionI2CSgp41.h>
#include <VOCGasIndexAlgorithm.h>
SensirionI2cScd4x scd41; SensirionI2CSgp41 sgp41; VOCGasIndexAlgorithm voc;
float lastT = 25, lastRH = 50; uint32_t t1 = 0, t5 = 0, cond = 0;

void setup() {
  Bridge.begin();
  Wire1.begin();                                   // Qwiic = Wire1
  scd41.begin(Wire1, SCD41_I2C_ADDR_62);
  scd41.stopPeriodicMeasurement(); delay(500);
  scd41.setAutomaticSelfCalibrationEnabled(0);     // il bus non vede mai 400 ppm: si calibra a mano (FRC)
  scd41.setSensorAltitude(240);                    // Torino ≈ 240 m
  scd41.startPeriodicMeasurement();
  sgp41.begin(Wire1); cond = millis();
}

void loop() {
  uint32_t now = millis();
  if (now - t1 >= 1000) {                          // l'algoritmo VOC vuole 1 Hz
    t1 = now; uint16_t rhT = lastRH * 65535 / 100, tT = (lastT + 45) * 65535 / 175, sv = 0, sn = 0;
    if (now - cond < 10000) sgp41.executeConditioning(rhT, tT, sv);
    else if (!sgp41.measureRawSignals(rhT, tT, sv, sn)) Bridge.notify("cabin_voc", sv, voc.process(sv));
  }
  if (now - t5 >= 5000) {
    t5 = now; bool ready = false;
    if (!scd41.getDataReadyStatus(ready) && ready) {
      uint16_t co2; float t, rh;
      if (!scd41.readMeasurement(co2, t, rh)) { lastT = t; lastRH = rh; Bridge.notify("cabin_co2", co2, t, rh); }
    }
  }
}
```

**Lato Python:** `Bridge.provide("cabin_co2", fn)`. La funzione `fn` aggiunge l'ora GPS e l'ultima posizione e scrive su `ts.db`.

**Cose da non fare con il Bridge**
- Mai chiamare `Bridge.call` dentro un callback `provide`: va in deadlock.
- Non aprire `/dev/ttyHS1` / `Serial1` a mano: li gestisce il router.

### 7.3 Posizionamento e qualità del dato

**Cabina** (subito, senza lavori sul bus)
- SCD41 + SGP41 ad altezza testa, lontani da porte, bocchette e dal calore della UNO Q (almeno 10–20 cm).
- Indicatore: **ventilazione e affollamento per linea e ora**. L'apertura delle porte si vede come un calo di CO2 a velocità zero.
- Riferimento: Barcellona 2022, CO2 media sui bus ~1000 ppm.

**Esterno** (versione 2)
- Ingresso sul tetto o sul fianco, lontano dallo scarico, rivolto in basso, con schermo antiradiazione.
- Si segnalano le misure PM con umidità > 85%: l'umidità gonfia le particelle e falsa la lettura.

**Risoluzione spaziale della CO2**
- L'SCD41 ha un tempo di risposta τ63 ≈ 60 s. Alla velocità commerciale media di Torino (~16 km/h) una lettura si "spalma" su ~270 m.
- Quindi la CO2 va **aggregata per tratto o esagono** (H3 risoluzione 9), mai mostrata per singolo punto.

**Calibrazione**
- **SCD41:** ricalibrazione forzata (FRC) all'aperto, in aria pulita.
  1. Almeno 3 minuti di misura stabile.
  2. `stopPeriodicMeasurement`.
  3. `performForcedRecalibration(target)`. Se restituisce `0xFFFF` è fallita.
  - Il target è ~430 ppm, oppure il valore di un NDIR di riferimento.
  - Ripetere dopo qualche giorno.
- **VOC/NOx** sono **indici relativi** (VOC base 100, NOx base 1): mai presentarli come ppb. Salvate anche i valori grezzi.
- **Confronto con le stazioni ARPA Piemonte di Torino** (Lingotto, Rubino, Rebaudengo = traffico, Grassi, Consolata) su PM e NO2. ARPA non dà un riferimento per la CO2.
  - Ogni volta che il bus passa entro ~100 m da una stazione si registra una coppia di confronto.
- I dati vanno etichettati come **"indicativi"**: la norma CEN/TS 17660-2 è pensata per postazioni fisse.

---

## 8. Struttura del repository

```
bussense/
├── README.md                     # come avviare demo, replay e mock in 3 comandi
├── contract/                     # ★ DA CONCORDARE PER PRIMA (ora 1)
│   ├── event_types.yaml          # tabella 5.1
│   ├── obs.v1.schema.json        # record JSONL (5.3)
│   ├── report_line.md            # formato BS1 (5.2)
│   ├── ts.v1.md                  # serie temporale (5.5)
│   └── examples/                 # file d'esempio validi, usati dai test
├── phone/
│   ├── SETUP_A26.md              # impostazioni Samsung, app, porte, hotspot
│   └── android-app/              # (dopo l'hackathon) app nativa Kotlin
├── unoq-app/                     # App di App Lab (in ~/ArduinoApps/bussense sulla scheda)
│   ├── app.yaml                  # brick: object_detection / video_object_detection, web_ui
│   ├── python/
│   │   ├── main.py               # avvio, Bridge.provide, App.run(user_loop=...)
│   │   ├── requirements.txt      # websocket-client, numpy, scipy, h3, opencv (se serve)
│   │   └── bussense/
│   │       ├── phone.py          # client snapshot/MJPEG + client WebSocket SensorServer
│   │       ├── sampler.py        # campionamento per distanza percorsa
│   │       ├── vision.py         # inferenza + ritaglio area strada
│   │       ├── imu.py            # riorientamento, filtri, buche, frenate, rugosità
│   │       ├── fusion.py         # fusione IMU↔visione, deduplica nel passaggio
│   │       ├── privacy.py        # oscuramento volti/targhe, fail-closed
│   │       ├── store.py          # SQLite WAL, JSONL, riga BS1, media, retention
│   │       ├── aggregate.py      # candidata→confermata→risolta
│   │       └── web/              # pagine WebUI: mappa Leaflet, stato, validazione
│   ├── sketch/
│   │   ├── sketch.ino            # sensori + Bridge.notify (+ in futuro supervisione alimentazione)
│   │   └── sketch.yaml
│   └── data/                     # (gitignored) /app/data
├── models/
│   ├── datasets.md               # RDD2022, GBS, licenze, come scaricarli
│   ├── train/                    # notebook Edge Impulse / script di export
│   └── cards/                    # model card: classi, precisione misurata, limiti
├── tools/
│   ├── record/                   # come registrare un giro (video + IMU + GPS + marcatore di sincronizzazione)
│   ├── replay/                   # rimanda un giro registrato sulle STESSE interfacce del telefono
│   ├── mock/                     # mock_phone.py, mock_events.py, mock_env.py
│   └── bench/                    # benchmark FPS e temperatura sulla UNO Q
├── server/                       # (stretch) FastAPI: ingest idempotente, GeoJSON, validazione
└── docs/
    ├── PIANO.md                  # questo documento
    ├── privacy/                  # DPIA-lite, informativa, cartello per il bus
    └── pitch/
```

**Il punto chiave è il replay:** `tools/replay` deve esporre gli **stessi endpoint** del telefono (snapshot HTTP + WebSocket con lo stesso JSON). Così l'intera UNO Q non distingue la demo dal mondo reale, e tutti possono sviluppare senza bus.

---

## 9. Piano di lavoro

### 9.1 Prima dell'hackathon (checklist)

**UNO Q**
- [ ] Aggiornare (App Lab 0.10.x, `arduino-app-cli system update`).
- [ ] Impostare la password, attivare SSH (`system network-mode enable`).
- [ ] Controllare lo spazio con `df -h`.
- [ ] **Scaricare in anticipo container e modelli:** il primo avvio li scarica e alla sede il Wi-Fi può essere lento.
- [ ] Dopo l'aggiornamento, **congelare le versioni**.

**Account**
- [ ] GitHub (repo con la struttura del §8).
- [ ] Edge Impulse (piano Developer gratuito: job da 60 min, 3 progetti privati).
- [ ] Roboflow (facoltativo), Tailscale.

**Dati**
- [ ] Scaricare RDD2022 (solo JP/IN/CZ, ~1,8 GB) e GBS (Zenodo).
- [ ] Estrarre da OSM i nodi `street_lamp`, i binari del tram e i dossi di Torino.
- [ ] Scaricare il GTFS di GTT.

**Giro registrato (fondamentale)**
- [ ] 20–40 min in auto per Torino, con il telefono sul supporto definitivo.
- [ ] Video 1080p30 + IMU/GPS (Sensor Logger).
- [ ] **Marcatore di sincronizzazione:** 3 colpi decisi sul telefono all'inizio, visibili sia nell'IMU sia nel video.
- [ ] Un giro di giorno e uno al crepuscolo.
- [ ] Etichettare 100–200 fotogrammi come test set "Torino".

**Primo modello**
- [ ] Addestrare il detector a 3 classi.
- [ ] Fare il deploy "UNO Q" da Edge Impulse.
- [ ] **Misurare gli FPS sulla scheda.**

**Materiale**
- [ ] Alimentatore USB-C PD 5 V/3 A (≥ 15 W; consigliato 45 W) + cavo da 3 A.
- [ ] Hub USB-C con PD passthrough (es. Arduino 8-in-1).
- [ ] Power bank PD.
- [ ] Sensori del §7.1 e cavi Qwiic↔Grove.
- [ ] Supporto telefono rigido + paraluce in silicone.
- [ ] **Stampe A3** di buche, cassonetti traboccanti e rifiuti.
- [ ] Telefono di riserva.

### 9.2 Prima ora: test sull'hardware (chiudono le incognite)

```bash
# 1. Wi-Fi: la UNO Q può fare da access point? (per il bus)
iw list | sed -n '/Supported interface modes/,/Band /p'        # serve "* AP"

# 2. Hotspot del telefono: collegarsi e trovare il telefono (è il gateway)
sudo nmcli dev wifi connect "bussense-a26" password "********"
PHONE=$(ip route | awk '/^default/{print $3}'); echo $PHONE
curl -s "http://$PHONE:4444/video/snapshot" -o test.jpg       # Android IP Camera, TLS disattivato
#   (con IP Webcam:  curl -s "http://$PHONE:8080/shot.jpg" -o test.jpg)

# 3. Cavo: telefono sull'hub alimentato → adb funziona? (piano B + supervisione)
sudo apt install adb && adb devices                           # accettare "Consenti sempre"; disattivare Auto Blocker se blocca
adb forward tcp:8081 tcp:8081                                 # SensorServer su localhost
lsusb -t                                                      # con "Tethering USB" attivo: classe 02/0D = NCM (ok), E0 = RNDIS (non va)

# 4. Orologio e disco
timedatectl; sudo hwclock -r; df -h

# 5. Temperatura sotto carico (durante il benchmark del modello)
cat /sys/class/thermal/thermal_zone*/temp
```

**Altre verifiche da fare nella prima ora:**
- [ ] Il Brick con `Camera("http://…")` apre davvero lo stream del telefono? La libreria usa FFmpeg ridotto **(da verificare)**.
- [ ] Le librerie Sensirion compilano su `arduino:zephyr`? Fare uno scanner I2C su `Wire1`.
- [ ] Identificare il modulo Seeed "VOC e CO2" che avete: il codice è stampato sulla scheda.
- [ ] **Soak test di 30 minuti a schermo spento** delle app del telefono.
- [ ] FPS reali del modello sulla UNO Q e temperatura.

### 9.3 Ruoli

| Ruolo | Responsabilità | 5 persone | 4 | 3 |
|---|---|---|---|---|
| **R1 Telefono & acquisizione** | Impostazioni A26, app, rete, `phone.py`, campionatore, registrazione e replay del giro | P1 | P1 | A |
| **R2 Edge AI** | Dataset, addestramento Edge Impulse, `vision.py`, fusione, privacy, benchmark | P2 | P2 | B |
| **R3 MCU, sensori, hardware** | Sketch, Bridge, SCD41/SGP41, supporto, alimentazione, in seguito spegnimento controllato | P3 | P3 | A |
| **R4 Dati & mappa** | `store.py`, `aggregate.py`, WebUI/Leaflet, export GeoJSON, (server) | P4 | P4 | C |
| **R5 Pitch, privacy, QA** | Storia, metriche sul test set, DPIA-lite e cartello, script della demo, prove | P5 | P4 | C |

**Telefono e IMU:** `imu.py` (buche e frenate) lo possono fare R1 o R2. Conviene **R1**, che ha i dati del giro.

### 9.4 Milestone (con "definizione di fatto")

| Milestone | Contenuto | Fatto quando |
|---|---|---|
| **M0 — contratto** (ora 1) | `contract/` approvato, mock funzionanti | Ognuno lancia `make mock` e vede eventi finti sulla mappa |
| **M1 — scheletro che cammina** | telefono → UNO Q → detector fittizio → riga BS1 + JSONL → puntino sulla mappa | Gira sull'hardware vero e sopravvive a un riavvio dell'App |
| **M2 — riconoscimento vero** | Modello a 3 classi ≥ 2 FPS + buche e frenate da IMU + deduplica | Il replay del giro produce eventi sensati; precisione misurata sul test set |
| **M3 — demo v1 congelata** | Replay, privacy attiva, avvio automatico, pannello stato, sensori su mappa | Dopo aver staccato la corrente torna su da solo in < 2 min; tag `v1-demo`; video di backup registrato |
| **M4 — stretch** | Lampioni, conferma su passaggi ripetuti, rumore, server/validazione, spegnimento controllato | Solo se M3 resta verde |
| **M5 — freeze** | Nessuna nuova funzione | 3 prove complete del pitch |

### 9.5 Programma 24 ore (T0 = inizio; CP = checkpoint di 15 min tutti insieme)

| Blocco | R1 Telefono | R2 Edge AI | R3 MCU/HW | R4 Dati & mappa | R5 Pitch/QA |
|---|---|---|---|---|---|
| T0–1 | **Tutti:** contratto v1, board dei task, repo, test della prima ora (§9.2) | | | | |
| T1–4 | Hotspot + app + `phone.py` (snapshot + WS) | Modello sulla UNO Q contro il video registrato; misura FPS | Scanner I2C, SCD41 → Bridge → Python | `store.py` + mappa WebUI con i mock | Struttura del pitch, stampe A3, informativa |
| **CP1 T4** | **M1: scheletro che cammina** | | | | |
| T4–8 | `imu.py`: riorientamento, buche, frenate; sync GPS↔foto | Modello vero, ritagli, deduplica | SGP41/SGP30, valori sulla serie temporale | Eventi live sulla mappa, filtri, dettaglio evento | Allineare il giro registrato, test set |
| **CP2 T8** | **M2: eventi reali end-to-end sul replay** | | | | |
| T8–12 | Replay sulle stesse interfacce; campionatore per distanza | Privacy (YuNet + targhe, fail-closed) | Run at startup, pannello stato (temperatura, disco, FPS) | Layer CO2/VOC per esagoni, export GeoJSON | Metriche, slide v1 |
| **CP3 T12** | **M3: demo v1 congelata + video di backup** | | | | |
| T12–16 | Sonno a turni (~3 h). Solo stretch a basso rischio: luce/lampioni, rugosità, conferma su passaggi | | | | |
| T16–18 | Caccia ai bug; si integra lo stretch solo se CP3 è ancora verde | | | | |
| **T18** | **Feature freeze (M5)**, prova 1 | | | | |
| T18–23 | Prove 2–3, domande e risposte, allestimento del banco demo, tile della mappa in cache | | | | |
| T23–24 | Margine e consegna | | | | |

### 9.6 Programma 48 ore

| Blocco | Focus |
|---|---|
| T0–12 (giorno 1) | Come il piano 24 h fino al CP3: **demo v1 congelata a T12** |
| T12–20 (notte 1) | Sonno a turni. R2 ri-addestra con i fotogrammi di Torino. R1+R3 lavorano sui lampioni (sensore di luce + mappa dei picchi). R4 fa la conferma su passaggi ripetuti con un simulatore: 50 passaggi su una linea GTT dal GTFS, con problemi che compaiono e spariscono. |
| **CP4 T20** | Integrazione, regressione sul replay |
| T20–32 (giorno 2) | Conferma/risoluzione su mappa. Pagina di validazione per i giudici (sì/no/non so). Spegnimento controllato al banco (interruttore che simula il quadro → salva → spegne → riparte). Prova sul campo in auto attorno alla sede. One-pager per GTT e Torino City Lab. |
| **CP5 T32** | Sistema completo a batteria, senza laptop |
| T32–38 | Rifinitura, metriche, slide v2. **Freeze a T38** |
| T38–48 | Prove, video di backup, sonno, allestimento, consegna |

### 9.7 Linea di taglio

| MVP (obbligatorio entro M3) | Stretch (solo se M3 è verde) |
|---|---|
| Flusso telefono → UNO Q (foto, GPS, IMU) | Lampioni spenti (sensore di luce + più notti) |
| Buche/frenate/sbandate da IMU + detector a 3 classi | `incident_candidate` con revisione umana |
| Ostacoli con COCO già presente | Conferma su passaggi ripetuti + "risolto" |
| Riga BS1 + JSONL + SQLite con GPS | Server + pagina di validazione + open data |
| CO2 (SCD41) + VOC sulla mappa | Rumore (SEN0232), modulo esterno SEN66 |
| Mappa locale + replay | Spegnimento controllato con supercondensatore |
| Privacy: niente video continuo, ritagli oscurati | VLM in cloud come seconda opinione |
| Avvio automatico + pannello stato | App nativa Android |

---

## 10. Strategia demo e pitch

**Demo (senza autobus)**
1. **Replay:** il giro registrato a Torino passa per le stesse interfacce del telefono. La mappa si riempie in tempo reale. Va etichettata onestamente: "REPLAY: giro reale a Torino del gg/mm".
2. **Dal vivo:** il telefono sul supporto inquadra una stampa A3 (buca o cassonetto traboccante) e in ~2 s compare il puntino sulla mappa. Un colpo sul tavolo genera un evento IMU.
3. **Ambiente:** soffiare sull'SCD41 fa salire la CO2 sopra i 2000 ppm in diretta.
4. **Pannello stato:** FPS, temperatura, ultimo fix GPS, spazio su disco.
5. **48 h:** l'interruttore "quadro" spegne e riaccende tutto in modo controllato.
6. **Backup:** video di 2 minuti su due laptop e una chiavetta; tutto funziona offline.

**Pitch (4 minuti)**

| Tempo | Contenuto |
|---|---|
| 20 s | **Gancio:** foto di una buca a Torino. "Gli autobus passano già ovunque, ogni giorno." |
| 30 s | **Problema:** segnalazioni lente e dipendenti dai cittadini. |
| 20 s | **Intuizione:** i passaggi ripetuti sono ispezioni gratuite e misurano anche i tempi di riparazione. I telefoni nei cassetti diventano sensori: 62 Mt di rifiuti elettronici nel 2022, solo il 22% riciclato. |
| 90 s | **Demo.** |
| 30 s | **Architettura:** una slide (telefono, i due processori della UNO Q, mappa). |
| 20 s | **Numeri:** precisione sul test set di Torino, km in replay, FPS, consumi (~3–6 W per la UNO Q). |
| 20 s | **Privacy by design.** |
| 20 s | **Costo e scala:** € per autobus, open data. |
| 10 s | **Prossimo passo:** pilota con Torino City Lab e GTT. |

---

## 11. Deploy sull'autobus (dopo l'hackathon)

### Alimentazione
- **Mai collegare i 24 V del bus al VIN della UNO Q** (massimo 24 V).
  - Un impianto "24 V" in marcia sta a 27–29 V.
  - Ha transitori di load dump fino a 58 V (con soppressione centrale) e oltre.
- Catena consigliata:
  1. Fusibile 5 A → TVS (SM8S36A).
  2. Convertitore ferroviario **Mean Well RSD-60L-12** (18–72 V in ingresso, certificato EN 50155).
  3. Rail a 12 V.
  4. **UPS a supercondensatore 5 V/3 A con pin di "power-fail"**.
  5. UNO Q (USB-C).
- Il telefono ha un suo caricatore USB-C PD per 12/24 V.
- **Lo STM32 fa da supervisore**:
  - legge il quadro (KL15) con un optoaccoppiatore;
  - quando il bus si spegne chiede a Linux di salvare e spegnersi (`poweroff`);
  - poi stacca un relè di mantenimento, così a bus fermo l'assorbimento è < 1 mA.
- **Pilota senza toccare l'impianto:** batteria LiFePO4 12,8 V 20 Ah in scatola V-0 (~17–19 h di autonomia), sostituita ogni notte.

### Montaggio
- **Telefono:** dentro, in alto sul parabrezza lato passeggeri, all'ombra dell'indicatore di linea, fuori dal campo visivo dell'autista e dalla zona del tergicristallo.
  - Supporto rigido su VHB, non a collo d'oca: vibra.
  - Paraluce in silicone contro i riflessi.
- **UNO Q:** in una scatola ventilata, fuori dal sole (limite di 60 °C), plastica non metallica, vicina al telefono.
- **Calore del telefono:** se si scalda troppo chiude la fotocamera. Usare 720p, schermo spento, posizione in ombra, e mettere in pausa l'acquisizione quando la temperatura sale.
- Nessuna luce accesa: coprire la matrice LED della UNO Q. Niente suoni. Rimovibile in pochi minuti.

### Affidabilità
- App in "Run at startup", oppure `systemd` con `Restart=always` e `WatchdogSec`.
- Watchdog hardware **(da verificare)** `ls /dev/watchdog*`.
- **Heartbeat ogni 60 s:** temperatura CPU, disco, FPS, età del fix GPS, stato del telefono.
- Riconnessione allo stream con backoff (1 → 30 s).
- Accesso remoto con **Tailscale** (funziona dietro il NAT del 5G). Aggiornamenti via `git` con rollback.

### Telefono A26 in servizio continuo
- Batteria "Senza restrizioni" per le app e app in "App mai in sospensione".
- "Metti in sospensione le app non usate" OFF.
- **Blocco schermo = Nessuno**, altrimenti dopo un riavvio le app non partono.
- Aggiornamenti automatici OFF.
- **Per l'autobus serve l'app nativa** impostata come launcher (Home):
  - da Android 15 un servizio fotocamera non può partire all'avvio da un `BOOT_COMPLETED`;
  - SensorServer non parte da solo al boot.

### Permessi
- **Torino City Lab** (Comune; programma Call4Testing / ToMove4Future) come porta d'ingresso verso:
  - **GTT**: ingegneria flotta, officina, DPO;
  - **Iren Smart Solutions**: lampioni;
  - **AMIAT**: rifiuti.
- Il dispositivo non tocca CAN né freni: probabilmente basta la marcatura CE EN 50498, senza omologazione E-mark. Va confermato con GTT.
- Assicurazione RC + convenzione o comodato con GTT.

### Costo
~€300–450 di hardware per autobus + ~€8/mese di dati.

---

## 12. Privacy, GDPR ed etica

**Misure tecniche (privacy by design, art. 25)**
- **Fotogrammi e audio solo in RAM** (< 2 s). **Mai video continuo, mai audio salvato:** si calcolano solo i dB.
- **Ritagli:** prima del salvataggio si oscurano volti e targhe con un riempimento pieno, non con una sfocatura leggera.
  - Volti: **YuNet** (OpenCV, MIT).
  - Targhe: **yolo-v9-t license plate** (open-image-models, MIT).
  - Se una persona occupa più del 15% del ritaglio, l'immagine si scarta.
  - Se l'oscuratore fallisce si salvano solo i metadati (**fail-closed**). Lo schema SQLite impone `redacted = 1`.
- **Niente foto da fermi** (fermate = persone in attesa). Zone privacy sul deposito, sulle scuole e sugli ospedali.
- **Nessun identificativo dell'autista o del turno.**
  - Traccia GPS e frenate potrebbero diventare controllo a distanza del lavoratore (art. 4 L. 300/1970).
  - Le frenate si pubblicano **solo come hotspot aggregati** (≥ 5 eventi in ≥ 3 giorni). La procedura art. 4 spetta a GTT.
- **Conservazione:** ritagli 14 giorni dopo la sync (oltre 72 h serve una giustificazione documentata); traccia 1 Hz 30 giorni.
- **Dati pubblici:** solo date (non orari), nessun `device_id`, ritagli solo di problemi confermati.

**Passi legali**
- **DPIA obbligatoria:** monitoraggio sistematico su larga scala di un'area pubblica, art. 35(3)(c).
- Cartello semplificato con QR verso l'informativa completa, **anche all'esterno del bus** (provvedimento Garante 2010 §4.4).
- Titolare del trattamento: GTT, Comune o un'associazione o università partner.

**Testo di esempio per il cartello**
> Autobus con rilevazione automatica dello stato della strada. Una fotocamera rileva buche, rifiuti abbandonati e lampioni guasti. Volti e targhe vengono oscurati a bordo prima di ogni salvataggio; nessuna registrazione audio. Titolare: [ente]. Finalità: manutenzione urbana e ricerca (citizen science). Conservazione: max 14 giorni a bordo. Informativa completa: [QR].

**Etica**
- Niente immagini di vittime.
- I graffiti si pubblicano senza immagine: in Italia non c'è libertà di panorama.
- Va dichiarato il bias di copertura: si vedono solo le strade servite dai bus.

---

## 13. Rischi e mitigazioni

| Rischio | Prob. | Impatto | Mitigazione |
|---|---|---|---|
| Samsung chiude le app / lo stream cade | Alta | Alta | Impostazioni del §11, soak test, riconnessione automatica, adb via cavo come supervisione, app nativa per il bus |
| Inferenza troppo lenta (< 1 FPS) | Media | Alta | Modello nano 320 px, campionamento per distanza, area strada; misurare prima dell'evento |
| Calo di accuratezza tra test web e scheda | Media | Alta | Resize identico all'impulso ("Fit shortest axis"), test set di Torino |
| L'App non parte senza camera fisica | Alta se ignorato | Alta | `devices: [remote_camera_0]` in `app.yaml` |
| Librerie Sensirion non compilano su Zephyr | Media | Media | Test nella prima ora; fallback SensorBridge USB |
| Falsi positivi (ombre, tombini, binari) | Alta | Media | Fusione IMU + visione, maschere OSM, conferma su più passaggi, validazione umana |
| GPS impreciso (portici, vie strette) | Media | Media | Salvare l'accuratezza, scartare > 15 m, raggi di deduplica 6–12 m |
| Ora sbagliata dopo un'interruzione di corrente | Alta | Media | Ora GPS del telefono, NTP, campo `ts_src` |
| Surriscaldamento (UNO Q > 60 °C, telefono) | Media | Media | Ombra, ventilazione, riduzione FPS sopra 70 °C di SoC |
| Lampioni inaffidabili | Alta | Bassa | Sono stretch; precisione prima della recall; ≥ 3 notti |
| Wi-Fi della sede assente | Media | Media | Tutto offline sulla UNO Q, hotspot del telefono, tile della mappa in cache |
| Integrazione tardiva | Media | Alta | Contratto all'ora 1, mock, checkpoint ogni ~4 h, freeze a T18/T38 |
| Licenze (AGPL Ultralytics, Edge Impulse solo prototipi) | Media | Media | Modello Edge Impulse o YOLOX (Apache-2.0) per il deploy; tutto open source |
| GDPR / rifiuto di GTT | Media | Alta | Privacy by design, DPIA, passare da Torino City Lab, pilota a batteria senza cablaggio |
| Guasto hardware il giorno della demo | Bassa | Alta | Telefono e cavi di riserva, video di backup |

---

## 14. Domande aperte da chiarire

1. **Durata dell'hackathon e griglia di valutazione dei giudici.** Chiedetele agli organizzatori.
2. **Quante persone siete e con quali competenze?** C'è qualcuno che sa sviluppare per Android (Kotlin)?
3. **Quale modulo Seeed esatto** avete per VOC/CO2? Se è l'SGP30, comprate un SCD41.
4. **Avete un hub USB-C con PD passthrough** e un alimentatore 5 V/3 A di qualità?
5. **Account Edge Impulse e un laptop con GPU** (oppure Colab) per l'addestramento?
6. **Quale categoria visiva principale:** buche o rifiuti? Il piano tiene entrambe nello stesso modello. Se il tempo stringe, si tengono solo le buche (visione + IMU).
7. **Open source:** il progetto sarà pubblicato interamente? Questo decide se Ultralytics/AGPL è accettabile.
8. **Dopo l'hackathon:** c'è un contatto in GTT o in un'università (PoliTo/UniTo) per un pilota?

---

## 15. Fonti principali

**Arduino UNO Q**
- Datasheet UNO Q (ABX00162/ABX00173): https://docs.arduino.cc/resources/datasheets/ABX00162-ABX00173-datasheet.pdf
- App Lab, Bricks e periferiche (codice sorgente): https://github.com/arduino/app-bricks-py
- CLI e verifica dei dispositivi delle App: https://github.com/arduino/arduino-app-cli
- Documentazione UNO Q e App Lab: https://github.com/arduino/docs-content
- Misure di consumo e prestazioni (Geerling): https://github.com/geerlingguy/sbc-reviews/issues/83
- FPS del telefono come camera della UNO Q: https://raspberry.tips/en/arduino/arduino-uno-q-smartphone-camera
- Edge Impulse ↔ App Lab: https://docs.edgeimpulse.com/hardware/deployments/run-arduino-app-lab
- Problema di accuratezza scheda vs web: https://forum.edgeimpulse.com/t/accuracy-difference-between-web-deployment-and-deployment-on-arduino-uno-q/17979

**Telefono e Android**
- Galaxy A26 5G: https://www.gsmarena.com/samsung_galaxy_a26-13679.php
- Samsung e app in background: https://dontkillmyapp.com/samsung
- Android 15, servizi in primo piano: https://developer.android.com/about/versions/15/behavior-changes-15
- SensorServer: https://github.com/UmerCodez/SensorServer
- Android IP Camera: https://f-droid.org/en/packages/com.github.digitallyrefined.androidipcamera/

**Dataset e ricerca**
- RDD2022: https://arxiv.org/abs/2209.08538
- GBS: https://zenodo.org/records/14711706
- Pothole Patrol: https://people.cs.rutgers.edu/~badri/553dir/papers/sensor/mobisys08.pdf
- Equilibrio dei passeggeri in frenata: https://pmc.ncbi.nlm.nih.gov/articles/PMC8343014/

**Sensori**
- Grove SGP30 (eCO2 ≠ CO2): https://wiki.seeedstudio.com/Grove-VOC_and_eCO2_Gas_Sensor-SGP30/
- SGP30 fuori produzione: https://sensirion.com/products/catalog/SGP30
- Grove SCD41: https://wiki.seeedstudio.com/Grove-CO2_&_Temperature_&_Humidity_Sensor-SCD41/
- Algoritmo degli indici VOC/NOx: https://github.com/Sensirion/gas-index-algorithm
- CO2 sui bus (Barcellona): https://doi.org/10.1016/j.envres.2021.112451
- Dati ARPA Piemonte: https://aria.ambiente.piemonte.it/qualita-aria/dati

**Privacy**
- Garante, FAQ videosorveglianza: https://www.garanteprivacy.it/faq/videosorveglianza
- EDPB, linee guida 3/2019: https://www.edpb.europa.eu/system/files/documents/files/file1/edpb_guidelines_201903_video_devices_en_0.pdf

**Torino e deploy**
- GTFS di GTT: https://aperto.comune.torino.it/dataset/feed-gtfs-trasporti-gtt
- Iren, carta del servizio illuminazione: https://www.gruppoiren.it/content/dam/iren/documents/it/i-nostri-servizi/smart-solutions/carta_del_servizio_illuminazione_pubblica.pdf
- Torino City Lab: https://www.torinocitylab.it/
- Load dump a 24 V: https://www.ti.com/lit/pdf/snoaaa1
- Mean Well RSD: https://www.meanwell.com/Upload/PDF/RSD-30/RSD-30-SPEC.PDF
- Citizen science, ECSA 10 principi: https://www.ecsa.ngo/10-principles/
