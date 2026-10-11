package it.bussense.phone

import android.graphics.Bitmap
import android.graphics.Matrix
import android.location.Location
import android.location.LocationManager
import android.os.SystemClock
import java.io.ByteArrayOutputStream
import kotlin.math.abs
import kotlin.math.max

/** Ora UTC dal GPS: offset = ora del fix (satelliti) - orologio di avvio del telefono. */
class GnssClock {
    @Volatile private var offsetMs: Long? = null

    fun update(loc: Location) {
        if (loc.provider == LocationManager.GPS_PROVIDER) offsetMs = loc.time - loc.elapsedRealtimeNanos / 1_000_000
    }

    /** (ora UTC in ms, fonte) per un istante espresso in elapsedRealtimeNanos. */
    fun utcMs(elapsedNs: Long): Pair<Long, String> {
        val off = offsetMs
        return if (off != null) (elapsedNs / 1_000_000 + off) to "gnss"
        else (System.currentTimeMillis() - (SystemClock.elapsedRealtimeNanos() - elapsedNs) / 1_000_000) to "phone"
    }
}

/** Decide quando tenere un fotogramma: ogni stepM metri percorsi, mai da fermi (privacy alle fermate). */
class FrameSampler(private val stepM: Double, private val demoIntervalMs: Long) {
    private var speed = 0.0
    private var lastNs = 0L
    private var dist = 0.0
    private var lastGrabNs = 0L

    @Synchronized fun onFix(loc: Location) { speed = if (loc.hasSpeed()) loc.speed.toDouble() else 0.0 }

    @Synchronized fun isDue(nowNs: Long): Boolean {
        if (demoIntervalMs > 0) return nowNs - lastGrabNs >= demoIntervalMs * 1_000_000
        if (lastNs != 0L) dist += speed * (nowNs - lastNs) / 1e9
        lastNs = nowNs
        return speed >= 0.5 && dist >= stepM
    }

    @Synchronized fun markGrabbed(nowNs: Long) { dist = 0.0; lastGrabNs = nowNs }
}

/** Ultime foto inviate, per allegare a un evento IMU la foto di ~1 s prima. */
class FrameRing(private val cap: Int) {
    class Frame(val elapsedNs: Long, val jpeg: ByteArray)
    private val q = ArrayDeque<Frame>()

    @Synchronized fun add(f: Frame) { q.addLast(f); while (q.size > cap) q.removeFirst() }

    @Synchronized fun around(targetNs: Long, maxDiffNs: Long): Frame? =
        q.minByOrNull { abs(it.elapsedNs - targetNs) }?.takeIf { abs(it.elapsedNs - targetNs) <= maxDiffNs }
}

object Img {
    /** Ruota secondo il sensore e ridimensiona a `width` px di larghezza. */
    fun prepare(src: Bitmap, rotation: Int, width: Int): Bitmap {
        val srcW = if (rotation % 180 == 0) src.width else src.height
        val s = width.toFloat() / srcW
        val m = Matrix().apply { postRotate(rotation.toFloat()); postScale(s, s) }
        return Bitmap.createBitmap(src, 0, 0, src.width, src.height, m, true)
    }

    fun jpeg(b: Bitmap, quality: Int): ByteArray =
        ByteArrayOutputStream().also { b.compress(Bitmap.CompressFormat.JPEG, quality, it) }.toByteArray()

    /** Nitidezza = varianza del Laplaciano su una copia piccola (160 px). Bassa = foto mossa. */
    fun sharpness(b: Bitmap): Double {
        val w = 160
        val h = max(3, b.height * w / b.width)
        val s = Bitmap.createScaledBitmap(b, w, h, true)
        val px = IntArray(w * h)
        s.getPixels(px, 0, w, 0, 0, w, h)
        val g = DoubleArray(w * h) {
            val c = px[it]
            0.299 * ((c shr 16) and 255) + 0.587 * ((c shr 8) and 255) + 0.114 * (c and 255)
        }
        var sum = 0.0
        var sq = 0.0
        var n = 0
        for (y in 1 until h - 1) for (x in 1 until w - 1) {
            val i = y * w + x
            val l = g[i - 1] + g[i + 1] + g[i - w] + g[i + w] - 4 * g[i]
            sum += l; sq += l * l; n++
        }
        val mean = sum / n
        return sq / n - mean * mean
    }
}
