package it.bussense.phone

import android.Manifest
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat

/** Schermata minima: indirizzo della UNO Q, modalità demo, avvia/ferma, stato. */
class MainActivity : ComponentActivity() {

    private lateinit var prefs: SharedPreferences
    private lateinit var urlField: EditText
    private lateinit var demoBox: CheckBox
    private lateinit var statusView: TextView
    private val ui = Handler(Looper.getMainLooper())

    private val permissions: Array<String>
        get() = buildList {
            add(Manifest.permission.CAMERA)
            add(Manifest.permission.ACCESS_FINE_LOCATION)
            if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
        }.toTypedArray()

    private val permLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
            if (hasPermissions()) startCapture()
            else statusView.text = "Servono i permessi di fotocamera e posizione (precisa)."
        }

    private val statusTick = object : Runnable {
        override fun run() {
            statusView.text = CaptureService.status
            ui.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = getSharedPreferences(Prefs.NAME, MODE_PRIVATE)
        val pad = (16 * resources.displayMetrics.density).toInt()

        urlField = EditText(this).apply {
            setText(prefs.getString(Prefs.URL, Prefs.DEFAULT_URL))
            hint = "ws://IP-UNO-Q:8765/phone"
            isSingleLine = true
        }
        demoBox = CheckBox(this).apply {
            text = "Modalità demo (1 foto/s anche da fermo)"
            isChecked = prefs.getBoolean(Prefs.DEMO, false)
        }
        statusView = TextView(this).apply { textSize = 16f }
        val start = Button(this).apply {
            text = "Avvia"
            setOnClickListener {
                prefs.edit()
                    .putString(Prefs.URL, urlField.text.toString().trim())
                    .putBoolean(Prefs.DEMO, demoBox.isChecked)
                    .apply()
                if (hasPermissions()) startCapture() else permLauncher.launch(permissions)
            }
        }
        val stop = Button(this).apply {
            text = "Ferma"
            setOnClickListener {
                prefs.edit().putBoolean(Prefs.AUTOSTART, false).apply()
                stopService(Intent(this@MainActivity, CaptureService::class.java))
            }
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            fitsSystemWindows = true
            setPadding(pad, pad, pad, pad)
            addView(TextView(this@MainActivity).apply { text = "BusSense · telefono"; textSize = 22f })
            addView(urlField)
            addView(demoBox)
            addView(start)
            addView(stop)
            addView(statusView)
        })

        // Usata come launcher sul bus: riparte da sola (l'activity è in primo piano,
        // quindi Android permette di avviare il servizio fotocamera).
        if (prefs.getBoolean(Prefs.AUTOSTART, false) && hasPermissions()) startCapture()
    }

    override fun onResume() {
        super.onResume()
        ui.post(statusTick)
    }

    override fun onPause() {
        ui.removeCallbacks(statusTick)
        super.onPause()
    }

    private fun hasPermissions() = listOf(Manifest.permission.CAMERA, Manifest.permission.ACCESS_FINE_LOCATION)
        .all { ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED }

    private fun startCapture() {
        prefs.edit().putBoolean(Prefs.AUTOSTART, true).apply()
        ContextCompat.startForegroundService(
            this,
            Intent(this, CaptureService::class.java)
                .putExtra(CaptureService.EXTRA_URL, prefs.getString(Prefs.URL, Prefs.DEFAULT_URL))
                .putExtra(CaptureService.EXTRA_DEMO, prefs.getBoolean(Prefs.DEMO, false))
        )
    }
}
