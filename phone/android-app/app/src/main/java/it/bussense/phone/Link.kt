package it.bussense.phone

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * WebSocket verso la UNO Q con riconnessione automatica.
 * - Eventi (reliable): tenuti in coda finché la UNO Q non risponde {"t":"ack","seq":N},
 *   e reinviati a ogni riconnessione.
 * - Traccia e foto (non reliable): se la rete è lenta vengono scartate.
 * - Se il telefono è collegato come CLIENT a un Wi-Fi senza internet (UNO Q access point),
 *   Android manderebbe il traffico sul 5G: il socket viene legato alla rete Wi-Fi.
 *   Con il telefono in modalità hotspot non serve: la UNO Q è sulla sua rete locale.
 */
class Link(ctx: Context, private val url: String, private val hello: () -> JSONObject) {

    private val cm = ctx.getSystemService(ConnectivityManager::class.java)
    private val base = OkHttpClient.Builder().pingInterval(10, TimeUnit.SECONDS).build()
    private val thread = HandlerThread("link").apply { start() }
    private val h = Handler(thread.looper)
    private val pending = LinkedHashMap<Long, String>()   // seq -> evento in attesa di ack

    @Volatile private var wifi: Network? = null
    @Volatile private var ws: WebSocket? = null
    @Volatile var connected = false
        private set
    @Volatile private var stopped = false
    private var backoffMs = 1000L
    private var reconnectScheduled = false

    private val netCb = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) { wifi = network }
        override fun onLost(network: Network) { if (wifi == network) wifi = null }
    }

    fun start() {
        val req = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) // anche Wi-Fi senza internet
            .build()
        cm.requestNetwork(req, netCb)
        h.post { connect() }
    }

    fun stop() {
        stopped = true
        ws?.close(1000, "stop")
        runCatching { cm.unregisterNetworkCallback(netCb) }
        thread.quitSafely()
    }

    fun pendingCount(): Int = synchronized(pending) { pending.size }

    fun send(seq: Long, msg: JSONObject, reliable: Boolean) {
        val text = msg.toString()
        if (reliable) synchronized(pending) {
            pending[seq] = text
            while (pending.size > 500) pending.remove(pending.keys.first())
        }
        val w = ws ?: return
        if (!connected) return
        if (!reliable && w.queueSize() > 1_000_000) return   // rete lenta: si perde la foto, non l'evento
        w.send(text)
    }

    private fun connect() {
        if (stopped) return
        reconnectScheduled = false
        val client = wifi?.let { base.newBuilder().socketFactory(it.socketFactory).build() } ?: base
        ws = client.newWebSocket(Request.Builder().url(url).build(), listener)
    }

    private fun scheduleReconnect() {
        h.post {
            if (stopped || reconnectScheduled) return@post
            reconnectScheduled = true
            h.postDelayed({ connect() }, backoffMs)
            backoffMs = (backoffMs * 2).coerceAtMost(30_000L)
        }
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            connected = true
            backoffMs = 1000L
            webSocket.send(hello().toString())
            val toResend = synchronized(pending) { pending.values.toList() }
            toResend.forEach { webSocket.send(it) }
            Log.i("BusSense", "collegato a $url, reinviati ${toResend.size} eventi")
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val m = runCatching { JSONObject(text) }.getOrNull() ?: return
            if (m.optString("t") == "ack") synchronized(pending) { pending.remove(m.optLong("seq")) }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            connected = false
            Log.w("BusSense", "connessione fallita: ${t.message}")
            scheduleReconnect()
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            connected = false
            scheduleReconnect()
        }
    }
}
