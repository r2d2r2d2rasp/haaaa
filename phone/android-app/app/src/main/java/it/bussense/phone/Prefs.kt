package it.bussense.phone

import android.content.SharedPreferences
import java.util.UUID

object Prefs {
    const val NAME = "bussense"
    const val URL = "url"
    const val DEMO = "demo"
    const val AUTOSTART = "autostart"
    private const val DEVICE_ID = "device_id"

    // Con la UNO Q come access point l'indirizzo è fisso; con l'hotspot del telefono
    // leggere l'IP della UNO Q con `hostname -I` e scriverlo nell'app.
    const val DEFAULT_URL = "ws://10.42.0.1:8765/phone"

    /** Id casuale e persistente: mai IMEI o numero di serie (privacy). */
    fun deviceId(p: SharedPreferences): String =
        p.getString(DEVICE_ID, null) ?: ("ph-" + UUID.randomUUID().toString().take(8)).also {
            p.edit().putString(DEVICE_ID, it).apply()
        }
}
