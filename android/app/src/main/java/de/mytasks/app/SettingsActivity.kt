package de.mytasks.app

import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

/**
 * Konfigurationsscreen: Server-URL + Anmeldemodus.
 *
 * Modus "token": Test-HEAD mit P-Access-Token-Headern.
 *  - 200 → Tokens verschlüsselt speichern, weiter zur Hauptansicht
 *  - 401/403 → Token abgelehnt, Meldung zeigen
 *
 * Modus "sso": Test-HEAD ohne Header (Redirects zur Pangolin-
 * Anmeldung werden gefolgt).
 *  - erreichbar → nur URL + Modus speichern, Login erfolgt im WebView
 *  - 401/403 → SSO-Schutz prüfen, Meldung zeigen
 */
class SettingsActivity : AppCompatActivity() {

    private lateinit var config: ConfigStore
    private val client by lazy {
        OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .build()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        config = ConfigStore(this)

        val urlInput = findViewById<EditText>(R.id.input_url)
        val idInput = findViewById<EditText>(R.id.input_token_id)
        val tokenInput = findViewById<EditText>(R.id.input_token)
        val tokenGroup = findViewById<LinearLayout>(R.id.token_group)
        val ssoHint = findViewById<TextView>(R.id.sso_hint)
        val modeToken = findViewById<RadioButton>(R.id.mode_token)
        val modeSso = findViewById<RadioButton>(R.id.mode_sso)
        val modeGroup = findViewById<RadioGroup>(R.id.auth_mode_group)
        val saveButton = findViewById<Button>(R.id.btn_save)
        val statusText = findViewById<TextView>(R.id.text_status)
        val progress = findViewById<ProgressBar>(R.id.progress)

        // Bestehende Werte vorbelegen (Tokens nur als Platzhalter, nie Klartext)
        urlInput.setText(config.serverUrl)
        if (config.useSso) {
            modeSso.isChecked = true
        } else {
            modeToken.isChecked = true
        }
        if (config.tokenId.isNotBlank()) {
            idInput.hint = getString(R.string.token_stored_placeholder)
            tokenInput.hint = getString(R.string.token_stored_placeholder)
        }

        // Modus-Umschaltung: Token-Felder nur im Token-Modus zeigen
        fun applyMode() {
            val sso = modeSso.isChecked
            tokenGroup.visibility = if (sso) View.GONE else View.VISIBLE
            ssoHint.visibility = if (sso) View.VISIBLE else View.GONE
        }
        modeGroup.setOnCheckedChangeListener { _, _ -> applyMode() }
        applyMode()

        saveButton.setOnClickListener {
            val url = urlInput.text.toString().trim()
            val sso = modeSso.isChecked
            val tokenId = idInput.text.toString().trim()
            val token = tokenInput.text.toString().trim()

            when {
                !url.startsWith("https://") -> {
                    statusText.text = getString(R.string.error_https_required)
                    return@setOnClickListener
                }
                // Bereits gespeicherte Tokens gelten weiter, wenn Felder leer bleiben
                !sso && tokenId.isBlank() && config.tokenId.isBlank() -> {
                    statusText.text = getString(R.string.error_token_id_missing)
                    return@setOnClickListener
                }
                !sso && token.isBlank() && config.token.isBlank() -> {
                    statusText.text = getString(R.string.error_token_missing)
                    return@setOnClickListener
                }
            }

            val effectiveId = tokenId.ifBlank { config.tokenId }
            val effectiveToken = token.ifBlank { config.token }

            progress.visibility = View.VISIBLE
            statusText.text = getString(R.string.status_testing)
            saveButton.isEnabled = false

            CoroutineScope(Dispatchers.IO).launch {
                val result = if (sso) {
                    testSsoConnection(url)
                } else {
                    testConnection(url, effectiveId, effectiveToken)
                }
                withContext(Dispatchers.Main) {
                    progress.visibility = View.GONE
                    saveButton.isEnabled = true
                    when (result) {
                        is TestResult.Success -> {
                            config.serverUrl = url
                            if (sso) {
                                config.authMode = ConfigStore.MODE_SSO
                                config.clearTokens()
                            } else {
                                config.authMode = ConfigStore.MODE_TOKEN
                                config.tokenId = effectiveId
                                config.token = effectiveToken
                            }
                            MainActivity.start(this@SettingsActivity)
                            finish()
                        }
                        is TestResult.Rejected -> {
                            if (sso) {
                                statusText.text = getString(
                                    R.string.error_sso_rejected,
                                    result.code,
                                )
                            } else {
                                config.clearTokens()
                                statusText.text = getString(
                                    R.string.error_token_rejected,
                                    result.code,
                                )
                            }
                        }
                        is TestResult.Unreachable -> {
                            statusText.text = getString(
                                R.string.error_unreachable,
                                result.detail.take(120),
                            )
                        }
                    }
                }
            }
        }
    }

    private sealed class TestResult {
        data object Success : TestResult()
        data class Rejected(val code: Int) : TestResult()
        data class Unreachable(val detail: String) : TestResult()
    }

    private fun testConnection(url: String, tokenId: String, token: String): TestResult {
        return try {
            val request = okhttp3.Request.Builder()
                .url(url)
                .header("P-Access-Token-Id", tokenId)
                .header("P-Access-Token", token)
                .head()
                .build()

            client.newCall(request).execute().use { resp ->
                when {
                    resp.isSuccessful -> TestResult.Success
                    resp.code == 401 || resp.code == 403 -> TestResult.Rejected(resp.code)
                    else -> TestResult.Success // z. B. Redirects von Pangolin sind ok
                }
            }
        } catch (e: Exception) {
            TestResult.Unreachable(e.message ?: e.javaClass.simpleName)
        }
    }

    /**
     * SSO-Modus: Test-HEAD ohne Header. Pangolin antwortet entweder mit
     * der App (bereits gültige Session/Cookie) oder leitet zur Anmeldung
     * um (Redirects werden gefolgt → 200 auf der Login-Seite = erreichbar).
     * Nur ein direktes 401/403 bedeutet: SSO-Schutz greift anders als erwartet.
     */
    private fun testSsoConnection(url: String): TestResult {
        return try {
            val request = okhttp3.Request.Builder()
                .url(url)
                .head()
                .build()

            client.newCall(request).execute().use { resp ->
                when {
                    resp.isSuccessful -> TestResult.Success
                    resp.code == 401 || resp.code == 403 -> TestResult.Rejected(resp.code)
                    else -> TestResult.Success
                }
            }
        } catch (e: Exception) {
            TestResult.Unreachable(e.message ?: e.javaClass.simpleName)
        }
    }
}
