# Protocollo telefono → UNO Q (v1)

## Trasporto

- **WebSocket**: `ws://<IP-UNO-Q>:8765/phone`.
- Il **telefono** fa da client: si collega e invia i messaggi.
- La **UNO Q** fa da server.
- Ogni messaggio è un **testo JSON**.
- **Riconnessione:** se la connessione cade, il telefono riprova con attese crescenti da 1 s fino a 30 s.
- **Ordinamento:** `seq` è un contatore crescente, uno per telefono.

## Campi comuni

Tutti i messaggi, tranne `hello`, hanno questi campi:

| Campo | Tipo | Significato |
|---|---|---|
| `v` | int | Versione del protocollo (1) |
| `t` | string | Tipo di messaggio: `hello` \| `track` \| `frame` \| `event` |
| `seq` | int | Contatore crescente del telefono |
| `device` | string | Id casuale del telefono (`ph-xxxxxxxx`). Non è l'IMEI. |
| `ts_ms` | int | Ora UTC in ms (epoch) |
| `ts_src` | string | Fonte dell'ora: `gnss` (orologio dei satelliti, via GPS_PROVIDER) oppure `phone` (orologio del telefono) |

## Campi di posizione

Sono facoltativi: il telefono li manda se ha un fix GPS.

| Campo | Significato |
|---|---|
| `lat`, `lon` | Posizione (WGS84) |
| `acc_m` | Accuratezza orizzontale, in metri |
| `speed_mps` | Velocità |
| `heading_deg` | Direzione |
| `fix_age_ms` | Età del fix rispetto al messaggio |

## Messaggi

### `hello`
Il telefono lo invia appena si collega.

```json
{"v":1,"t":"hello","device":"ph-1a2b3c4d","app_ver":"0.1.0","model":"SM-A266B","android":35}
```

### `track`
Una volta al secondo, a ogni fix GPS.

Contiene la posizione e le statistiche IMU dell'ultimo secondo:

| Campo | Significato |
|---|---|
| `imu.az_rms_ms2` | Vibrazione verticale (RMS) |
| `imu.decel_max_ms2` | Massima decelerazione longitudinale |
| `imu.latacc_max_ms2` | Massima accelerazione laterale |
| `imu.n` | Numero di campioni |
| `imu.fwd_calibrated` | Indica se l'asse "avanti" è già stato appreso |

```json
{"v":1,"t":"track","seq":101,"device":"ph-1a2b3c4d","ts_ms":1791642231284,"ts_src":"gnss",
 "lat":45.0705,"lon":7.6869,"acc_m":4.8,"speed_mps":6.2,"heading_deg":87,"fix_age_ms":3,
 "imu":{"az_rms_ms2":0.42,"decel_max_ms2":0.3,"latacc_max_ms2":0.2,"n":100,"fwd_calibrated":true}}
```

### `frame`
Una foto scelta dal telefono in base alla distanza percorsa: circa una ogni 4 m. Le foto mosse vengono scartate.

- Si **può perdere**: non richiede conferma.
- La UNO Q la usa per il riconoscimento e la tiene **solo in RAM**.

```json
{"v":1,"t":"frame","seq":102,"device":"…","ts_ms":…,"ts_src":"gnss","lat":…,"lon":…,
 "sharp":87.3,"w":640,"h":360,"jpeg_b64":"/9j/4AAQ…"}
```

### `event`
Un evento rilevato dal telefono: `cls` = `pothole` | `harsh_braking` | `swerve`.

- **Richiede conferma:** la UNO Q risponde `{"t":"ack","seq":<seq>}`.
- Il telefono lo reinvia a ogni riconnessione finché non riceve l'ack.
- Può includere la foto più vicina a circa 1 s prima dell'evento:
  - `jpeg_b64` contiene la foto;
  - `frame_dt_ms` indica quanti ms prima dell'evento è stata scattata.

```json
{"v":1,"t":"event","seq":103,"device":"…","ts_ms":…,"ts_src":"gnss","lat":…,"lon":…,"acc_m":5.1,
 "cls":"pothole","src":"imu","conf":0.71,"severity":2,
 "imu":{"p2p_ms2":11.2,"thr_ms2":9.0,"speed_mps":7.4,"gyro_rads":0.8},
 "frame_dt_ms":940,"jpeg_b64":"/9j/…"}
```

## Risposte della UNO Q

| Risposta | Quando |
|---|---|
| `{"t":"ack","seq":N}` | Dopo ogni `event`, anche se l'evento era un duplicato |
| `{"t":"hello_ack","server":"bussense-unoq","v":1}` | Dopo `hello` |

## Compatibilità

- Il **replay** (`tools/replay`) e il **mock** (`tools/mock/mock_phone.py`) parlano esattamente questo protocollo.
- Un telefono più vecchio che non fa pre-elaborazione può mandare solo `track` e `frame`: la UNO Q funziona lo stesso.
