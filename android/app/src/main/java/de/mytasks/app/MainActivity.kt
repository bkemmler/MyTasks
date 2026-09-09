package de.mytasks.app

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.os.Bundle
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/**
 * Hauptansicht: WebView auf MyTasks hinter Pangolin.
 *
 * Modus "token" — Header-Strategie (P-Access-Token-Id / P-Access-Token):
 *  1. Navigation:        loadUrl(url, headers)
 *  2. GET-Subressourcen: shouldInterceptRequest → OkHttp mit Headern → WebResourceResponse
 *  3. fetch/XHR aus JS:  inject.js patcht window.fetch + XMLHttpRequest (POST-Bodies
 *                        sind im Intercept nicht zugreifbar)
 *  Header werden ausschließlich an den konfigurierten Host gesendet,
 *  externe Hosts öffnen den Systembrowser.
 *
 * Modus "sso" — Pangolin-SSO-Login direkt im WebView:
 *  Keine Header, keine Intercepts. Die Sitzung läuft über Cookies;
 *  alle Navigationen (inkl. Pangolin-Anmeldeseite auf fremdem Host)
 *  bleiben im WebView, bis die App erreicht ist.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var config: ConfigStore
    private lateinit var webView: WebView
    private lateinit var progress: ProgressBar
    private lateinit var errorView: TextView
    private lateinit var errorBox: View
    private lateinit var retryButton: Button
    private lateinit var settingsButton: View

    private val client by lazy {
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .followRedirects(false) // Redirects manuell: keine Headers an Fremd-Hosts
            .build()
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        config = ConfigStore(this)

        // Ohne Konfiguration → Settings-Screen
        if (!config.isConfigured) {
            startSettings(freshStart = true)
            return
        }

        webView = findViewById(R.id.webview)
        progress = findViewById(R.id.progress)
        errorView = findViewById(R.id.text_error)
        retryButton = findViewById(R.id.btn_retry)
        settingsButton = findViewById(R.id.btn_open_settings)
        errorBox = findViewById(R.id.error_box)

        // Nur in Debug-APKs: Remote-Debugging via Desktop-Chrome
        // (chrome://inspect) — Console + Netzwerk-Tab zeigen die echte
        // Fehlerzeile bei „failed to fetch". Release-Builds: aus.
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true   // localStorage-Tokens der SPA
        // SSO-Modus braucht Session-Cookies (Pangolin-Anmeldung).
        // Third-Party-Cookies sind nötig, falls das Session-Cookie auf der
        // Pangolin-Auth-Domain liegt und die API auf der Ressourcen-Domain.
        // Im Token-Modus unbedenklich: Es werden nie Cookies für Auth genutzt
        // (Header), WebView-Cookies enthalten dort keine Geheimnisse.
        val cookieManager = CookieManager.getInstance()
        cookieManager.setAcceptCookie(true)
        cookieManager.setAcceptThirdPartyCookies(webView, true)
        webView.settings.userAgentString =
            "${webView.settings.userAgentString} MyTasksAndroid/${BuildConfig.VERSION_NAME}"

        // JS-Bridge: inject.js meldet 401/403 aus fetch/XHR → Token-Fenster.
        // Sicher: nur im authentifizierten WebView aktiv, Methode zeigt nur UI.
        webView.addJavascriptInterface(AuthBridge(), "MTAuth")

        webView.webViewClient = object : WebViewClient() {

            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest,
            ): Boolean {
                // SSO: Anmelde-Flow läuft über Pangolin-Hosts — alles bleibt
                // im WebView, bis die Session steht (keine Geheimnisse im Spiel).
                if (config.useSso) return false
                // Token-Modus: Externe Hosts im Systembrowser statt im
                // authentifizierten WebView
                return request.url.host != config.allowedHost
            }

            override fun shouldInterceptRequest(
                view: WebView,
                request: WebResourceRequest,
            ): WebResourceResponse? {
                // SSO: keine Header zu injizieren — WebView + Cookies genügen
                if (!config.hasTokens) return null
                val method = request.method.uppercase()
                if (method != "GET" && method != "HEAD") return null
                if (request.url.host != config.allowedHost) return null
                return interceptGet(request)
            }

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                progress.visibility = View.VISIBLE
                errorBox.visibility = View.GONE
            }

            override fun onPageFinished(view: WebView, url: String) {
                progress.visibility = View.GONE
                // Schicht 3: fetch/XHR-Patch für API-Calls
                view.evaluateJavascript(injectScript, null)
            }

            override fun onReceivedHttpError(
                view: WebView,
                request: WebResourceRequest,
                errorResponse: WebResourceResponse,
            ) {
                // Nur Haupt-Navigation reagiert auf 401/403 — Subressourcen
                // (Favicon etc.) dürfen nicht die App blockieren.
                if (request.isForMainFrame &&
                    (errorResponse.statusCode == 401 || errorResponse.statusCode == 403)
                ) {
                    handleAuthRejected()
                }
            }
        }

        retryButton.setOnClickListener { loadApp() }
        settingsButton.setOnClickListener { startSettings() }

        // ⚙-Overlay: jederzeit in die Token-Konfiguration
        findViewById<View>(R.id.btn_gear).setOnClickListener { startSettings() }

        loadApp()
    }

    private val injectScript: String by lazy {
        val js = assets.open("inject.js").bufferedReader().use { it.readText() }
        // Globale Variablen vor dem Patch setzen (Tokens nur im WebView-Prozess,
        // niemals in Logs oder Cookies). SSO: leerer Host → inject.js
        // beendet sich sofort, nativer fetch/EventSource mit Cookies läuft.
        val signingHost = if (config.hasTokens) config.allowedHost ?: "" else ""
        val globals = """
            window.__MT_HOST = ${jsonString(signingHost)};
            window.__MT_TOKEN_ID = ${jsonString(config.tokenId)};
            window.__MT_TOKEN = ${jsonString(config.token)};
        """.trimIndent()
        "(function(){ $globals $js })();"
    }

    private fun jsonString(s: String): String =
        "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\""

    private fun loadApp() {
        if (config.useSso || !config.hasTokens) {
            // SSO: plain laden — Pangolin leitet ggf. zur Anmeldung um,
            // danach landet die Session-Cookie-gestützt auf der App.
            webView.loadUrl(config.serverUrl)
        } else {
            // Schicht 1: Navigation mit Headern
            webView.loadUrl(
                config.serverUrl,
                mapOf(
                    "P-Access-Token-Id" to config.tokenId,
                    "P-Access-Token" to config.token,
                ),
            )
        }
    }

    /** Schicht 2: GET/HEAD selbst per OkHttp ausführen, Header injizieren. */
    private fun interceptGet(request: WebResourceRequest): WebResourceResponse? {
        return try {
            val builder = Request.Builder()
                .url(request.url.toString())
                .header("P-Access-Token-Id", config.tokenId)
                .header("P-Access-Token", config.token)

            request.requestHeaders.forEach { (k, v) ->
                if (!k.equals("P-Access-Token-Id", true) && !k.equals("P-Access-Token", true)) {
                    builder.header(k, v)
                }
            }

            client.newCall(builder.build()).execute().use { resp ->
                if (resp.isRedirect || resp.body == null) return null

                val contentType = resp.header("Content-Type")?.let {
                    val parts = it.split(";")
                    parts[0].trim() to parts.getOrNull(1)?.trim()?.removePrefix("charset=")
                } ?: ("application/octet-stream" to null)

                val bodyBytes = resp.body!!.bytes()
                WebResourceResponse(
                    contentType.first,
                    contentType.second,
                    resp.code,
                    resp.message.ifBlank { "OK" },
                    resp.headers.toMap(),
                    bodyBytes.inputStream(),
                )
            }
        } catch (e: Exception) {
            null // WebView übernimmt den Request dann selbst
        }
    }

    /** Pangolin-Ablehnung erkennen und zum Config-Screen führen. */
    private fun handleAuthRejected() {
        runOnUiThread {
            errorView.text = getString(
                if (config.useSso) {
                    R.string.error_sso_rejected_short
                } else {
                    R.string.error_token_rejected_short
                },
            )
            errorBox.visibility = View.VISIBLE
        }
    }

    /**
     * JS-Bridge für inject.js: meldet 401/403 aus fetch/XHR-Calls der SPA.
     * Kann ausschließlich das Token-Fenster anzeigen — keine Daten, keine
     * Rückgabewerte. Nur im authentifizierten WebView geladen (externe Hosts
     * öffnen den Systembrowser).
     */
    private inner class AuthBridge {
        @JavascriptInterface
        fun expired(status: Int) {
            runOnUiThread { handleAuthRejected() }
        }
    }

    private fun startSettings(freshStart: Boolean = false) {
        val intent = Intent(this, SettingsActivity::class.java)
        startActivity(intent)
        if (freshStart) finish()
    }

    companion object {
        fun start(activity: Activity) {
            activity.startActivity(Intent(activity, MainActivity::class.java))
        }
    }

    override fun onBackPressed() {
        if (::webView.isInitialized && webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }
}
