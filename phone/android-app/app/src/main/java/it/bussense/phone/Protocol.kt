package it.bussense.phone

import android.location.Location
import android.os.Build
import android.os.SystemClock
import android.util.Base64
import org.json.JSONObject

/** Messaggi del protocollo contract/phone_link.v1.md. */
object Protocol {
    private const val V = 1
    private const val APP_VER = "0.1.0"

    fun hello(device: String): JSONObject = JSONObject()
        .put("v", V).put("t", "hello").put("device", device)
        .put("app_ver", APP_VER).put("model", Build.MODEL).put("android", Build.VERSION.SDK_INT)

    fun track(seq: Long, device: String, tsMs: Long, tsSrc: String, loc: Location, imu: JSONObject): JSONObject =
        base("track", seq, device, tsMs, tsSrc).pos(loc).put("imu", imu)

    fun frame(seq: Long, device: String, tsMs: Long, tsSrc: String, loc: Location?,
              sharp: Double, w: Int, h: Int, jpeg: ByteArray): JSONObject =
        base("frame", seq, device, tsMs, tsSrc).pos(loc)
            .put("sharp", sharp).put("w", w).put("h", h)
            .put("jpeg_b64", Base64.encodeToString(jpeg, Base64.NO_WRAP))

    /** frame = (ms tra foto ed evento, jpeg) oppure null. */
    fun event(seq: Long, device: String, tsMs: Long, tsSrc: String, loc: Location?,
              ev: ImuEvent, frame: Pair<Long, ByteArray>?): JSONObject {
        val o = base("event", seq, device, tsMs, tsSrc).pos(loc)
            .put("cls", ev.cls).put("src", "imu").put("conf", ev.conf).put("severity", ev.severity)
            .put("imu", JSONObject(ev.info))
        if (frame != null) {
            o.put("frame_dt_ms", frame.first)
            o.put("jpeg_b64", Base64.encodeToString(frame.second, Base64.NO_WRAP))
        }
        return o
    }

    private fun base(t: String, seq: Long, device: String, tsMs: Long, tsSrc: String) = JSONObject()
        .put("v", V).put("t", t).put("seq", seq).put("device", device)
        .put("ts_ms", tsMs).put("ts_src", tsSrc)

    private fun JSONObject.pos(loc: Location?): JSONObject {
        if (loc == null) return this
        put("lat", loc.latitude)
        put("lon", loc.longitude)
        if (loc.hasAccuracy()) put("acc_m", loc.accuracy.toDouble())
        if (loc.hasSpeed()) put("speed_mps", loc.speed.toDouble())
        if (loc.hasBearing()) put("heading_deg", loc.bearing.toDouble())
        put("fix_age_ms", (SystemClock.elapsedRealtimeNanos() - loc.elapsedRealtimeNanos) / 1_000_000)
        return this
    }
}
