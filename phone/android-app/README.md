# BusSense: app Android (livello 1 di pre-elaborazione)

## Cosa fa il telefono

**GPS**
- Legge il GPS a 1 Hz.
- L'ora viene dai satelliti, perché si usa `GPS_PROVIDER`.

**Sensori di movimento (IMU) a 100 Hz**
- **Asse verticale:** lo ricava dalla gravità, quindi non importa come è montato il telefono.
- **Asse "avanti" del bus:** lo impara dalle accelerazioni e frenate rilevate dal GPS. Gli serve qualche minuto di guida.
- **Eventi rilevati:**
  - `pothole`: picco-picco verticale su 0,3 s, con soglia diversa per fascia di velocità; sotto i 10 km/h si ignora;
  - `harsh_braking`: decelerazione ≥ 1,5 m/s² per ≥ 0,5 s; gravità 1–3 a seconda del picco;
  - `swerve`: accelerazione laterale ≥ 2 m/s² sopra i 15 km/h.

**Fotocamera**
- Tiene **una foto ogni 4 m percorsi**.
- Da fermo non scatta, per la privacy alle fermate.
- Le foto mosse vengono scartate (varianza del Laplaciano).
- Le foto tenute vengono ridotte a 640 px e compresse in JPEG con qualità 80.

**Invio alla UNO Q (WebSocket)**
- Il protocollo è descritto in [`contract/phone_link.v1.md`](../../contract/phone_link.v1.md).
- Gli eventi restano in coda finché la UNO Q non conferma di averli ricevuti.
- Foto e traccia GPS si possono perdere se la rete è lenta.

> **Le soglie sono stime.** Tarale con un giro registrato. La schermata mostra lo stato; i valori `p2p_ms2` e `sharp` arrivano nei messaggi.

## Compilare e installare

1. Apri la cartella `phone/android-app` in **Android Studio** (Ladybug o più recente). La sincronizzazione Gradle scarica tutto da sola.
2. Sul Galaxy A26 attiva le opzioni sviluppatore (Impostazioni → Info sul telefono → Informazioni software → tocca 7 volte "Numero build") e il **Debug USB**.
3. Collega il telefono al PC e premi ▶ Run.

> Lo scheletro **non è ancora stato compilato**. Se Android Studio segnala errori, di solito sono versioni delle librerie: accetta gli aggiornamenti che propone.

## Usarla

**1. Rete**
- Hotspot dell'A26 attivo e UNO Q collegata.
- Sulla UNO Q leggi il suo indirizzo con `hostname -I`.

**2. Indirizzo nell'app**
- Scrivi `ws://<IP-UNO-Q>:8765/phone`.
- Se la UNO Q fa da access point, l'indirizzo è `ws://10.42.0.1:8765/phone`.

**3. Modalità demo**
- Spunta **"Modalità demo"** per le prove al tavolo: manda 1 foto al secondo anche da fermo.

**4. Avvio**
- Premi **Avvia** e concedi fotocamera, posizione precisa e notifiche.

**5. Impostazioni Samsung (indispensabili)**
- Impostazioni → Batteria → Limiti utilizzo in background:
  - "Metti in sospensione app non usate" **OFF**;
  - aggiungi BusSense ad **"App mai in sospensione"**.
- App → BusSense → Batteria: **Senza restrizioni**.
- Blocco schermo: **Nessuno**. Serve sul bus: dopo un riavvio le app non partono finché il telefono è bloccato.

**6. Sul bus**
- Nel `AndroidManifest.xml` togli il commento al blocco `HOME` e imposta BusSense come schermata Home.
- Così dopo un riavvio l'app riparte da sola e riavvia la raccolta.

## Prossimi passi (livello 2 e 3)

- **Livello 2:** detector LiteRT int8 a 320 px sul telefono.
  - Manda `cls` e `bbox` insieme alla foto, con `src: "vision"`.
  - Da aggiungere in `onImage`.
- **Livello 3:** oscuramento di volti e targhe sul telefono, prima dell'invio.
