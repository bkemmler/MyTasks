# MyTasks Android-App

**Version:** 1.2.4 (`versionCode 8`) — [GitHub Releases](https://github.com/bkemmler/MyTasks/releases)

Schlanke WebView-App für MyTasks hinter [Pangolin](https://github.com/fosrl/pangolin) mit zwei Anmeldemodi: Access-Token oder Pangolin-SSO.

## Anmeldemodi

| Modus | Für wen | Wie |
|---|---|---|
| **Access-Token** (Share-Link) | Token aus Pangolin (Resource → Share Links / Access Tokens) | App sendet bei **jedem** Request die Header `P-Access-Token-Id` / `P-Access-Token` |
| **Pangolin-SSO** | Pangolin-Benutzerkonto | Einmaliges Login auf der Pangolin-Seite direkt im App-Fenster, Sitzung bleibt per Cookie |

## Funktionsweise (Token-Modus)

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
| 3. API-Calls (`fetch`/XHR/SSE) | POST/PATCH/DELETE + Events der SPA | injiziertes JavaScript patcht `fetch` + `XMLHttpRequest` + `EventSource` |

Im **SSO-Modus** entfallen alle drei Schichten: Das WebView lädt plain, Pangolin leitet ggf. zur Anmeldung um (bleibt im App-Fenster, auch bei fremdem Auth-Host), danach läuft die Sitzung über Cookies. `inject.js` deaktiviert sich selbst (leerer Host → Early-Return, nativer `fetch`/`EventSource` mit Cookies).

**Sicherheit:**
- Tokens/Modus liegen in **EncryptedSharedPreferences** (AES256-GCM, Hardware-Masterkey)
- `allowBackup=false` — keine Tokens über Device-Backups
- Token-Modus: Header werden **ausschließlich an den konfigurierten Host** gesendet (Host-Allowlist), externe Links öffnen den Systembrowser
- SSO-Modus: keine Geheimnisse in der App, nur die Pangolin-Session-Cookies im WebView
- Nur HTTPS (`usesCleartextTraffic=false`, Network-Security-Config)
- Tokens erscheinen nie in URLs oder Logs

## Konfiguration

1. App starten → beim ersten Start öffnet sich der Konfigurationsscreen
2. Modus wählen und eintragen:
   - **Access-Token**: Server-URL + **P-Access-Token-Id** und **P-Access-Token** aus Pangolin
   - **Pangolin-SSO**: nur Server-URL — das Login erfolgt nach dem Speichern im App-Fenster
3. „Verbinden & speichern" — die App macht einen Test-Request:
   - ✅ Erfolg → Hauptansicht
   - **Access-Token**: ❌ HTTP 401/403 → „Token abgelehnt", Zugangsdaten prüfen
   - **Pangolin-SSO**: Der Test prüft nur die Erreichbarkeit — ein 401 („noch nicht angemeldet") ist normal. Nach dem Speichern erscheint die Pangolin-Anmeldung (Benutzer, Kennwort, MFA) direkt im App-Fenster. Nur bei Netzwerk-/TLS-Fehlern wird blockiert.

Tokens laufen ab? Die App erkennt das **automatisch** — sowohl beim Laden (HTTP 401/403 der Hauptseite) als auch mitten in der Sitzung (API-Calls der Weboberfläche werden über eine JS-Bridge überwacht). Es erscheint sofort das Token-Fenster; über ⚙ oben rechts kommst du jederzeit in die Konfiguration. Dort genügt es, nur das neue Token einzutragen — Server-URL und Token-Id bleiben erhalten, wenn die Felder leer bleiben. Im SSO-Modus genügt „Erneut versuchen" für eine frische Anmeldung.

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
│   ├── build.gradle.kts              minSdk 26, targetSdk 35
│   └── src/main/
│       ├── AndroidManifest.xml       INTERNET-Permission, HTTPS-only
│       ├── assets/inject.js          fetch/XHR/SSE-Header-Patch (Schicht 3)
│       └── java/de/mytasks/app/
│           ├── MainActivity.kt       WebView + Token/SSO-Modi + 401-Handling
│           ├── SettingsActivity.kt   Modus-Auswahl + Verbindungstest
│           └── ConfigStore.kt        authMode + EncryptedSharedPreferences
└── gradle/wrapper/
```

## Voraussetzungen

- Android 8.0+ (minSdk 26)
- MyTasks hinter Pangolin mit aktiviertem Schutz auf der Ressource (Access-Token- *oder* SSO-Auth — je nach gewähltem Anmeldemodus)
- Gültiges TLS-Zertifikat (Let's Encrypt o. ä.) — selbstsignierte Zertifikate werden abgelehnt
