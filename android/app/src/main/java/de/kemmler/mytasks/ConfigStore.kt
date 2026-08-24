package de.kemmler.mytasks

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.net.URL

/**
 * Verschlüsselte Konfiguration: Server-URL + Pangolin-Access-Token.
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

    val isConfigured: Boolean
        get() = serverUrl.startsWith("https://") && tokenId.isNotBlank() && token.isNotBlank()

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
        private const val KEY_URL = "server_url"
        private const val KEY_TOKEN_ID = "p_access_token_id"
        private const val KEY_TOKEN = "p_access_token"
    }
}
