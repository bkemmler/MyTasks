package de.mytasks.app

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.net.URL

/**
 * Verschlüsselte Konfiguration: Server-URL + Anmeldemodus.
 *
 * Modi: "token" (Pangolin-Access-Token per Request-Header, inkl.
 * Share-Links) oder "sso" (Pangolin-SSO-Login im WebView, Session
 * via Cookies — keine Tokens nötig).
 *
 * EncryptedSharedPreferences mit Hardware-gestütztem MasterKey;
 * allowBackup=false im Manifest verhindert zusätzlich die Ausleitung
 * über Device-Backups.
 */
class ConfigStore(context: Context) {

    private val prefs: SharedPreferences by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        EncryptedSharedPreferences.create(
            context,
            "mytasks_secure_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    var serverUrl: String
        get() = prefs.getString(KEY_URL, "") ?: ""
        set(value) = prefs.edit().putString(KEY_URL, value.trimEnd('/')).apply()

    var tokenId: String
        get() = prefs.getString(KEY_TOKEN_ID, "") ?: ""
        set(value) = prefs.edit().putString(KEY_TOKEN_ID, value.trim()).apply()

    var token: String
        get() = prefs.getString(KEY_TOKEN, "") ?: ""
        set(value) = prefs.edit().putString(KEY_TOKEN, value.trim()).apply()

    var authMode: String
        get() = prefs.getString(KEY_AUTH_MODE, MODE_TOKEN) ?: MODE_TOKEN
        set(value) = prefs.edit().putString(KEY_AUTH_MODE, value).apply()

    val useSso: Boolean
        get() = authMode == MODE_SSO

    val hasTokens: Boolean
        get() = tokenId.isNotBlank() && token.isNotBlank()

    val isConfigured: Boolean
        get() = serverUrl.startsWith("https://") && (useSso || hasTokens)

    /** Host-Allowlist für Header-Injection: nur dieser Host bekommt Tokens. */
    val allowedHost: String?
        get() = try {
            URL(serverUrl).host
        } catch (e: Exception) {
            null
        }

    fun clearTokens() {
        prefs.edit().remove(KEY_TOKEN_ID).remove(KEY_TOKEN).apply()
    }

    companion object {
        const val MODE_TOKEN = "token"
        const val MODE_SSO = "sso"

        private const val KEY_URL = "server_url"
        private const val KEY_TOKEN_ID = "p_access_token_id"
        private const val KEY_TOKEN = "p_access_token"
        private const val KEY_AUTH_MODE = "auth_mode"
    }
}
