package de.kemmler.mytasks

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.os.Bundle
import android.view.View
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
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
 * Header-Strategie (P-Access-Token-Id / P-Access-Token):
 *  1. Navigation:        loadUrl(url, headers)
 *  2. GET-Subressourcen: shouldInterceptRequest → OkHttp mit Headern → WebResourceResponse
 *  3. fetch/XHR aus JS:  inject.js patcht window.fetch + XMLHttpRequest (POST-Bodies
 *                        sind im Intercept nicht zugreifbar)
 *
 * Header werden ausschließlich an den konfigurierten Host gesendet.
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

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true   // localStorage-Tokens der SPA
        webView.settings.userAgentString =
            "${webView.settings.userAgentString} MyTasksAndroid/${BuildConfig.VERSION_NAME}"

        webView.webViewClient = object : WebViewClient() {

            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest,
            ): Boolean {
                // Externe Hosts im Systembrowser statt im authentifizierten WebView
                return request.url.host != config.allowedHost
            }

            override fun shouldInterceptRequest(
                view: WebView,
                request: WebResourceRequest,
            ): WebResourceResponse? {
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

        loadApp()
    }

    private val injectScript: String by lazy {
        val js = assets.open("inject.js").bufferedReader().use { it.readText() }
        // Globale Variablen vor dem Patch setzen (Tokens nur im WebView-Prozess,
        // niemals in Logs oder Cookies).
        val globals = """
            window.__MT_HOST = ${jsonString(config.allowedHost ?: "")};
            window.__MT_TOKEN_ID = ${jsonString(config.tokenId)};
            window.__MT_TOKEN = ${jsonString(config.token)};
        """.trimIndent()
        "(function(){ $globals $js })();"
    }

    private fun jsonString(s: String): String =
        "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\""

    private fun loadApp() {
        // Schicht 1: Navigation mit Headern
        webView.loadUrl(
            config.serverUrl,
            mapOf(
                "P-Access-Token-Id" to config.tokenId,
                "P-Access-Token" to config.token,
            ),
        )
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
            errorView.text = getString(R.string.error_token_rejected_short)
            errorBox.visibility = View.VISIBLE
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
