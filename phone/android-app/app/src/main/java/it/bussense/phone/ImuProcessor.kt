package it.bussense.phone

import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Handler
import android.os.HandlerThread
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sign
import kotlin.math.sqrt

data class ImuEvent(
    val cls: String,            // pothole | harsh_braking | swerve
    val conf: Double,
    val severity: Int,          // 1..3
    val elapsedNs: Long,        // stesso orologio di SensorEvent.timestamp (elapsedRealtimeNanos)
    val info: Map<String, Any>,
)

/**
 * Pre-elaborazione IMU (livello 1), a ~100 Hz:
 *  1. stima la gravità -> asse verticale, indipendente da come è montato il telefono;
 *  2. apprende l'asse "avanti" del bus dalle variazioni di velocità GPS;
 *  3. rileva buche (picco-picco verticale su 0,3 s, soglia per fascia di velocità),
 *     frenate brusche e sbandate (con isteresi e durata minima).
 * TUTTE LE SOGLIE SONO STIME: vanno tarate con il giro registrato.
 */
class ImuProcessor(
    private val sm: SensorManager,
    private val onEvent: (ImuEvent) -> Unit,
) : SensorEventListener {

    private val thread = HandlerThread("imu").apply { start() }

    private val g = DoubleArray(3)
    private var gInit = false
    private val fwdAcc = DoubleArray(3)
    private var fwdSamples = 0
    val forwardCalibrated get() = fwdSamples > FWD_MIN_SAMPLES

    @Volatile private var speed = 0.0
    @Volatile private var gpsAccel = 0.0
    private var prevSpeed = Double.NaN
    private var prevSpeedNs = 0L

    private var lonLp = 0.0
    private var latLp = 0.0
    private var vertLp = 0.0
    private val vertWin = ArrayDeque<Pair<Long, Double>>()
    @Volatile private var gyroMag = 0.0

    private var lastPotholeNs = 0L
    private var brakeStartNs = -1L
    private var brakePeak = 0.0
    private var swerveStartNs = -1L
    private var swervePeak = 0.0

    private val statsLock = Any()
    private var sSq = 0.0
    private var sN = 0
    private var sDecel = 0.0
    private var sLat = 0.0

    companion object {
        private const val FWD_MIN_SAMPLES = 300
        private const val BRAKE_ON = 1.5      // m/s²: soglia "rischio passeggeri in piedi"
        private const val BRAKE_OFF = 1.2
        private const val SWERVE_ON = 2.0
        private const val SWERVE_OFF = 1.6
    }

    fun start() {
        val h = Handler(thread.looper)
        sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)?.let { sm.registerListener(this, it, 10_000, h) } // 100 Hz
        sm.getDefaultSensor(Sensor.TYPE_GYROSCOPE)?.let { sm.registerListener(this, it, 10_000, h) }     // se manca: solo accelerometro
    }

    fun stop() {
        sm.unregisterListener(this)
        thread.quitSafely()
    }

    /** Chiamata a ogni fix GPS (1 Hz). */
    fun onGpsSpeed(v: Double, ns: Long) {
        if (!prevSpeed.isNaN()) {
            val dt = (ns - prevSpeedNs) / 1e9
            if (dt in 0.5..3.0) gpsAccel = (v - prevSpeed) / dt
        }
        prevSpeed = v
        prevSpeedNs = ns
        speed = v
    }

    /** Statistiche dell'ultimo secondo, allegate al messaggio "track". */
    fun drainStats(): JSONObject = synchronized(statsLock) {
        val o = JSONObject()
            .put("az_rms_ms2", if (sN > 0) sqrt(sSq / sN) else 0.0)
            .put("decel_max_ms2", sDecel)
            .put("latacc_max_ms2", sLat)
            .put("n", sN)
            .put("fwd_calibrated", forwardCalibrated)
        sSq = 0.0; sN = 0; sDecel = 0.0; sLat = 0.0
        o
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    override fun onSensorChanged(e: SensorEvent) {
        when (e.sensor.type) {
            Sensor.TYPE_GYROSCOPE -> gyroMag = sqrt((e.values[0] * e.values[0] + e.values[1] * e.values[1] + e.values[2] * e.values[2]).toDouble())
            Sensor.TYPE_ACCELEROMETER -> onAccel(e.values, e.timestamp)
        }
    }

    private fun onAccel(a: FloatArray, ns: Long) {
        if (!gInit) { for (i in 0..2) g[i] = a[i].toDouble(); gInit = true; return }
        for (i in 0..2) g[i] += 0.01 * (a[i] - g[i])           // passa-basso ~1 s: gravità
        val gn = norm(g)
        if (gn < 1e-3) return
        val up = DoubleArray(3) { g[it] / gn }
        val lin = DoubleArray(3) { a[it] - g[it] }
        val vert = dot(lin, up)
        val hor = DoubleArray(3) { lin[it] - vert * up[it] }

        // asse "avanti": media delle accelerazioni orizzontali, col segno della variazione di velocità GPS
        val ga = gpsAccel
        val v = speed
        if (abs(ga) > 0.8 && v > 2.0) {
            val s = sign(ga)
            for (i in 0..2) fwdAcc[i] += s * hor[i]
            fwdSamples++
        }
        var lon = ga        // finché l'asse non è calibrato si usa l'accelerazione GPS (1 Hz)
        var lat = 0.0
        if (forwardCalibrated) {
            val proj = dot(fwdAcc, up)
            val f = DoubleArray(3) { fwdAcc[it] - proj * up[it] }
            val fn = norm(f)
            if (fn > 1e-6) {
                for (i in 0..2) f[i] /= fn
                lon = dot(hor, f)
                lat = dot(hor, cross(up, f))
            }
        }
        lonLp += 0.05 * (lon - lonLp)       // ~0,2 s: toglie le vibrazioni
        latLp += 0.05 * (lat - latLp)
        vertLp += 0.5 * (vert - vertLp)     // taglia sopra ~20 Hz

        vertWin.addLast(ns to vertLp)
        while (vertWin.isNotEmpty() && ns - vertWin.first().first > 300_000_000L) vertWin.removeFirst()
        var mn = Double.MAX_VALUE
        var mx = -Double.MAX_VALUE
        for ((_, x) in vertWin) { if (x < mn) mn = x; if (x > mx) mx = x }
        val p2p = mx - mn

        synchronized(statsLock) {
            sSq += vert * vert; sN++
            sDecel = max(sDecel, -lonLp)
            sLat = max(sLat, abs(latLp))
        }
        detectPothole(p2p, ns, v)
        detectBrake(-lonLp, ns, v)
        detectSwerve(abs(latLp), ns, v)
    }

    // soglia picco-picco verticale per fascia di velocità (STIMA da tarare)
    private fun potholeThreshold(v: Double) = when {
        v < 5.6 -> 8.0     // < 20 km/h
        v < 8.3 -> 9.0     // 20–30 km/h
        v < 11.1 -> 10.0   // 30–40 km/h
        else -> 11.0
    }

    private fun detectPothole(p2p: Double, ns: Long, v: Double) {
        if (v < 2.8 || ns - lastPotholeNs < 1_000_000_000L) return    // < 10 km/h: ignorato
        val thr = potholeThreshold(v)
        if (p2p < thr) return
        lastPotholeNs = ns
        vertWin.clear()
        val conf = 0.5 + 0.5 * min(1.0, (p2p - thr) / thr)
        val sev = when { p2p > 1.6 * thr -> 3; p2p > 1.25 * thr -> 2; else -> 1 }
        onEvent(ImuEvent("pothole", conf, sev, ns,
            mapOf("p2p_ms2" to p2p, "thr_ms2" to thr, "speed_mps" to v, "gyro_rads" to gyroMag)))
    }

    private fun detectBrake(decel: Double, ns: Long, v: Double) {
        if (decel >= BRAKE_ON && (v > 1.0 || brakeStartNs >= 0)) {
            if (brakeStartNs < 0) { brakeStartNs = ns; brakePeak = 0.0 }
            brakePeak = max(brakePeak, decel)
        } else if (brakeStartNs >= 0 && decel < BRAKE_OFF) {
            val durMs = (ns - brakeStartNs) / 1e6
            if (durMs >= 500) {
                val sev = when { brakePeak >= 3.5 -> 3; brakePeak >= 2.5 -> 2; else -> 1 }
                onEvent(ImuEvent("harsh_braking", min(1.0, 0.5 + brakePeak / 7.0), sev, brakeStartNs,
                    mapOf("peak_ms2" to brakePeak, "dur_ms" to durMs, "fwd_calibrated" to forwardCalibrated)))
            }
            brakeStartNs = -1L
        }
    }

    private fun detectSwerve(latAcc: Double, ns: Long, v: Double) {
        if (!forwardCalibrated) return
        if (latAcc >= SWERVE_ON && (v > 4.2 || swerveStartNs >= 0)) {   // > 15 km/h
            if (swerveStartNs < 0) { swerveStartNs = ns; swervePeak = 0.0 }
            swervePeak = max(swervePeak, latAcc)
        } else if (swerveStartNs >= 0 && latAcc < SWERVE_OFF) {
            val durMs = (ns - swerveStartNs) / 1e6
            if (durMs >= 300) {
                onEvent(ImuEvent("swerve", min(1.0, 0.5 + swervePeak / 6.0), if (swervePeak >= 3.0) 3 else 2, swerveStartNs,
                    mapOf("peak_ms2" to swervePeak, "dur_ms" to durMs)))
            }
            swerveStartNs = -1L
        }
    }

    private fun dot(a: DoubleArray, b: DoubleArray) = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    private fun norm(a: DoubleArray) = sqrt(dot(a, a))
    private fun cross(a: DoubleArray, b: DoubleArray) = doubleArrayOf(
        a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
}
