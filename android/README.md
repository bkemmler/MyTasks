# MyTasks Android-App

Schlanke WebView-App für MyTasks hinter [Pangolin](https://github.com/fosrl/pangolin) mit Access-Token-Authentifizierung per Request-Headern.

## Funktionsweise

Die App lädt die MyTasks-Weboberfläche in einem WebView und sendet bei **jedem** Request die Pangolin-Header:

```
P-Access-Token-Id: <deine Token-Id>
P-Access-Token: <dein Token>
```

Drei Injektions-Schichten stellen das sicher:

| Schicht | Abgedeckt | Mechanismus |
|---|---|---|
| 1. Navigation | Hauptseite | `WebView.loadUrl(url, headers)` |
| 2. GET-Assets (JS/CSS/Bilder) | statische Dateien | `shouldInterceptRequest` → OkHttp mit Headern |
| 3. API-Calls (`fetch`/XHR) | POST/PATCH/DELETE der SPA | injiziertes JavaScript patcht `fetch` + `XMLHttpRequest` |

**Sicherheit:**
- Tokens liegen in **EncryptedSharedPreferences** (AES256-GCM, Hardware-Masterkey)
- `allowBackup=false` — keine Tokens über Device-Backups
- Header werden **ausschließlich an den konfigurierten Host** gesendet (Host-Allowlist), externe Links öffnen den Systembrowser
- Nur HTTPS (`usesCleartextTraffic=false`, Network-Security-Config)
- Tokens erscheinen nie in URLs oder Logs

## Konfiguration

1. App starten → beim ersten Start öffnet sich der Konfigurationsscreen
2. Eintragen:
   - **Server-URL**: deine Pangolin-Ressource, z. B. `https://mytaskapp.example.com`
   - **P-Access-Token-Id** und **P-Access-Token**: aus Pangolin (Resource → Share Links / Access Tokens)
3. „Verbinden & speichern" — die App macht einen Test-Request:
   - ✅ Erfolg → Hauptansicht
   - ❌ HTTP 401/403 → „Token abgelehnt", Zugangsdaten prüfen

Tokens laufen ab? Die App erkennt 401/403 beim Laden und zeigt „Token ungültig oder abgelaufen" — dann im Pangolin-Portal einen neuen Token erzeugen und unter ⚙ aktualisieren.

## Build (Android Studio)

1. Ordner `android/` in Android Studio öffnen (**File → Open**, dann das `android`-Verzeichnis wählen)
2. Gradle-Sync abwarten
3. **Build → Build Bundle(s)/APK(s) → Build APK(s)**
4. APK liegt unter `app/build/outputs/apk/debug/app-debug.apk` und lässt sich auf das Gerät kopieren/installieren

Für einen Release-Build: **Build → Generate Signed Bundle/APK** mit eigenem Keystore.

## Projektstruktur

```
android/
├── settings.gradle.kts
├── build.gradle.kts
├── app/
│   ├── build.gradle.kts              minSdk 26, targetSdk 34
│   └── src/main/
│       ├── AndroidManifest.xml       INTERNET-Permission, HTTPS-only
│       ├── assets/inject.js          fetch/XHR-Header-Patch (Schicht 3)
│       └── java/de/kemmler/mytasks/
│           ├── MainActivity.kt       WebView + Header-Injection + 401-Handling
│           ├── SettingsActivity.kt   Konfiguration + Verbindungstest
│           └── ConfigStore.kt        EncryptedSharedPreferences
└── gradle/wrapper/
```

## Voraussetzungen

- Android 8.0+ (minSdk 26)
- MyTasks hinter Pangolin mit aktiviertem Access-Token-Schutz auf der Ressource
- Gültiges TLS-Zertifikat (Let's Encrypt o. ä.) — selbstsignierte Zertifikate werden abgelehnt
