package it.bussense.phone

import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.ServiceInfo
// IMU DISATTIVATA: import usato solo dall'ImuProcessor
// import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle
import android.os.Looper
import android.os.SystemClock
// IMU DISATTIVATA: usato solo dal log degli eventi IMU
// import android.util.Log
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleService
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicLong

/**
 * Servizio in primo piano (camera|location): legge GPS, IMU e fotocamera, fa la
 * pre-elaborazione "livello 1" e invia tutto alla UNO Q.
 *
 * Va avviato mentre l'activity è visibile: da Android 14 un servizio fotocamera non
 * può partire dal background. Per questo è START_NOT_STICKY e sul bus l'app fa da launcher.
 *
 * NOTA: la lettura dell'IMU è temporaneamente DISATTIVATA (codice commentato). Restano
 * attivi GPS, fotocamera e invio alla UNO Q. Il messaggio "track" porta comunque il blocco
 * "imu" previsto dal contratto, con valori a zero e "disabled": true.
 */
class CaptureService : LifecycleService() {

    companion object {
        const val EXTRA_URL = "url"
        const val EXTRA_DEMO = "demo"
        @Volatile var status: String = "fermo"
        // IMU DISATTIVATA: TAG usato solo dal log degli eventi IMU
        // private const val TAG = "BusSense"
        private const val JPEG_WIDTH = 640
        private const val JPEG_QUALITY = 80
        private const val MIN_SHARPNESS = 15.0   // varianza del Laplaciano: da tarare guardando i valori "sharp"
        private const val STEP_M = 4.0           // una foto ogni 4 m percorsi
    }

    // parte dall'ora attuale: resta crescente anche dopo un riavvio dell'app
    private val seq = AtomicLong(System.currentTimeMillis())
    private val clock = GnssClock()
    private val frames = FrameRing(6)
    private val camExec = Executors.newSingleThreadExecutor()
    private lateinit var sampler: FrameSampler
    private lateinit var link: Link
    // IMU DISATTIVATA
    // private lateinit var imu: ImuProcessor
    private lateinit var deviceId: String
    private lateinit var lm: LocationManager
    @Volatile private var lastFix: Location? = null
    @Volatile private var nFrames = 0
    @Volatile private var nEvents = 0
    private var started = false

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        if (started) return START_NOT_STICKY
        started = true
        startInForeground()

        val prefs = getSharedPreferences(Prefs.NAME, MODE_PRIVATE)
        deviceId = Prefs.deviceId(prefs)
        val url = intent?.getStringExtra(EXTRA_URL) ?: prefs.getString(Prefs.URL, Prefs.DEFAULT_URL)!!
        val demo = intent?.getBooleanExtra(EXTRA_DEMO, false) ?: false

        sampler = FrameSampler(stepM = STEP_M, demoIntervalMs = if (demo) 1000 else 0)
        link = Link(this, url) { Protocol.hello(deviceId) }.also { it.start() }
        // IMU DISATTIVATA
        // imu = ImuProcessor(getSystemService(SensorManager::class.java), ::onImuEvent).also { it.start() }
        startLocation()
        startCamera()
        updateStatus()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        if (started) {
            lm.removeUpdates(locListener)
            // IMU DISATTIVATA
            // imu.stop()
            link.stop()
        }
        camExec.shutdown()
        status = "fermo"
        super.onDestroy()
    }

    private fun startInForeground() {
        val ch = "bussense"
        getSystemService(NotificationManager::class.java)
            .createNotificationChannel(NotificationChannel(ch, "BusSense", NotificationManager.IMPORTANCE_LOW))
        val n = NotificationCompat.Builder(this, ch)
            .setContentTitle("BusSense attivo")
            .setContentText("Raccolta dati in corso")
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setOngoing(true)
            .build()
        val type = if (Build.VERSION.SDK_INT >= 30)
            ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA or ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION else 0
        ServiceCompat.startForeground(this, 1, n, type)
    }

    // ---------------- GPS ----------------

    private val locListener = object : LocationListener {
        override fun onLocationChanged(location: Location) = onFix(location)
        override fun onProviderEnabled(provider: String) {}
        override fun onProviderDisabled(provider: String) {}
        @Deprecated("Deprecated in Java")
        override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
    }

    @SuppressLint("MissingPermission") // permessi chiesti da MainActivity
    private fun startLocation() {
        lm = getSystemService(LocationManager::class.java)
        // GPS_PROVIDER (non "fused"): l'ora del fix viene dai satelliti
        lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000L, 0f, locListener, Looper.getMainLooper())
    }

    private fun onFix(loc: Location) {
        clock.update(loc)
        sampler.onFix(loc)
        // IMU DISATTIVATA
        // imu.onGpsSpeed(if (loc.hasSpeed()) loc.speed.toDouble() else 0.0, loc.elapsedRealtimeNanos)
        lastFix = loc
        val (ts, src) = clock.utcMs(loc.elapsedRealtimeNanos)
        val s = seq.incrementAndGet()
        link.send(s, Protocol.track(s, deviceId, ts, src, loc, imuStatsDisabled()), reliable = false)
        updateStatus()
    }

    /** Blocco "imu" a zero finché la lettura dei sensori resta disattivata. */
    private fun imuStatsDisabled(): JSONObject = JSONObject()
        .put("az_rms_ms2", 0.0)
        .put("decel_max_ms2", 0.0)
        .put("latacc_max_ms2", 0.0)
        .put("n", 0)
        .put("fwd_calibrated", false)
        .put("disabled", true)

    // ---------------- Fotocamera ----------------

    private fun startCamera() {
        val future = ProcessCameraProvider.getInstance(this)
        future.addListener({
            val provider = future.get()
            val analysis = ImageAnalysis.Builder()
                .setResolutionSelector(
                    ResolutionSelector.Builder().setResolutionStrategy(
                        ResolutionStrategy(Size(1280, 720), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)
                    ).build()
                )
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                .build()
            analysis.setAnalyzer(camExec, ::onImage)
            provider.unbindAll()
            provider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, analysis)
        }, ContextCompat.getMainExecutor(this))
    }

    /** Chiamata per ogni fotogramma: se ne tiene uno ogni STEP_M metri, solo se nitido. */
    private fun onImage(proxy: ImageProxy) {
        proxy.use {
            val now = SystemClock.elapsedRealtimeNanos()
            if (!sampler.isDue(now)) return
            val bmp = Img.prepare(it.toBitmap(), it.imageInfo.rotationDegrees, JPEG_WIDTH)
            val sharp = Img.sharpness(bmp)
            if (sharp < MIN_SHARPNESS) return          // foto mossa: si riprova col fotogramma successivo
            sampler.markGrabbed(now)
            val jpeg = Img.jpeg(bmp, JPEG_QUALITY)
            frames.add(FrameRing.Frame(now, jpeg))
            val (ts, src) = clock.utcMs(now)
            val s = seq.incrementAndGet()
            link.send(s, Protocol.frame(s, deviceId, ts, src, lastFix, sharp, bmp.width, bmp.height, jpeg), reliable = false)
            nFrames++
        }
    }

    // ---------------- Eventi IMU (DISATTIVATI) ----------------

    /* IMU DISATTIVATA: nessun evento viene generato finché i sensori restano spenti.
    /** Chiamata dal thread IMU: allega posizione e la foto di ~1 s prima, poi invia con conferma. */
    private fun onImuEvent(ev: ImuEvent) {
        val (ts, src) = clock.utcMs(ev.elapsedNs)
        val frame = frames.around(ev.elapsedNs - 1_000_000_000L, maxDiffNs = 1_500_000_000L)
        val s = seq.incrementAndGet()
        link.send(s, Protocol.event(s, deviceId, ts, src, lastFix, ev, frame?.let { (ev.elapsedNs - it.elapsedNs) / 1_000_000 to it.jpeg }), reliable = true)
        nEvents++
        Log.i(TAG, "evento ${ev.cls} conf=${"%.2f".format(ev.conf)} sev=${ev.severity}")
    }
    */

    private fun updateStatus() {
        val fix = lastFix
        status = buildString {
            append(if (link.connected) "UNO Q: collegata" else "UNO Q: NON collegata")
            append("\nGPS: ").append(fix?.let { if (it.hasAccuracy()) "±%.0f m".format(it.accuracy) else "ok" } ?: "in attesa del fix")
            append("\nFoto inviate: ").append(nFrames)
            append("\nEventi: ").append(nEvents).append(" (in attesa di conferma: ").append(link.pendingCount()).append(")")
            append("\nIMU: disattivata")
            // IMU DISATTIVATA
            // append("\nAsse avanti calibrato: ").append(if (imu.forwardCalibrated) "sì" else "no (servono accelerazioni/frenate)")
        }
    }
}
