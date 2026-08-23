import { useEffect, useState } from "react";
import { api } from "../lib/api";

interface MailConfig {
  smtp_host: string;
  smtp_port: number;
  smtp_security: string;
  smtp_username: string | null;
  has_password: boolean;
  from_address: string;
  from_name: string | null;
}

export function Settings() {
  const [cfg, setCfg] = useState<MailConfig | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  // Formular-Drafts
  const [host, setHost] = useState("");
  const [port, setPort] = useState(587);
  const [security, setSecurity] = useState("starttls");
  const [username, setUsername] = useState("");
  const [fromAddress, setFromAddress] = useState("");
  const [fromName, setFromName] = useState("");

  const load = async () => {
    try {
      const res = await api<MailConfig>("/auth/me/mail-config");
      setCfg(res);
      setHost(res.smtp_host);
      setPort(res.smtp_port);
      setSecurity(res.smtp_security);
      setUsername(res.smtp_username ?? "");
      setFromAddress(res.from_address);
      setFromName(res.from_name ?? "");
    } catch {
      setCfg(null);
    } finally {
      setLoaded(true);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    if (!host || !fromAddress) {
      setMessage({ ok: false, text: "Server und Absenderadresse sind Pflicht." });
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const res = await api<MailConfig>("/auth/me/mail-config", {
        method: "PUT",
        body: JSON.stringify({
          smtp_host: host,
          smtp_port: port,
          smtp_security: security,
          smtp_username: username || null,
          smtp_password: password || null,
          from_address: fromAddress,
          from_name: fromName || null,
        }),
      });
      setCfg(res);
      setPassword("");
      setMessage({ ok: true, text: "Konfiguration gespeichert." });
    } catch (e) {
      setMessage({ ok: false, text: `Speichern fehlgeschlagen: ${e}` });
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setMessage(null);
    try {
      const res = await api<{ success: boolean; to?: string; detail?: string }>(
        "/auth/me/mail-config/test",
        { method: "POST", body: JSON.stringify({}) },
      );
      setMessage(
        res.success
          ? { ok: true, text: `Test-Email an ${res.to} versendet.` }
          : { ok: false, text: `Test fehlgeschlagen${res.detail ? `: ${res.detail}` : ""}.` },
      );
    } catch (e) {
      setMessage({ ok: false, text: `Test fehlgeschlagen: ${e}` });
    } finally {
      setTesting(false);
    }
  };

  const remove = async () => {
    if (!confirm("Mail-Konfiguration wirklich löschen? Keine E-Mails werden mehr versendet.")) return;
    try {
      await api("/auth/me/mail-config", { method: "DELETE" });
      setCfg(null);
      setHost("");
      setUsername("");
      setPassword("");
      setFromAddress("");
      setFromName("");
      setMessage({ ok: true, text: "Konfiguration gelöscht." });
    } catch (e) {
      setMessage({ ok: false, text: `Löschen fehlgeschlagen: ${e}` });
    }
  };

  if (!loaded) return <div className="text-stone-500">Lade…</div>;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">Einstellungen</h2>

      <section className="rounded-lg border border-stone-200 p-4 dark:border-stone-800">
        <div className="mb-1 flex items-center justify-between">
          <h3 className="font-semibold">E-Mail-Versand</h3>
          <span
            className={`text-xs ${cfg?.has_password || cfg ? "text-green-600" : "text-stone-400"}`}
          >
            {cfg ? "konfiguriert" : "nicht konfiguriert"}
          </span>
        </div>
        <p className="mb-4 text-xs text-stone-500">
          Eigene SMTP-Zugangsdaten für Test-Emails und die tägliche Zusammenfassung.
          Ohne Konfiguration werden keine E-Mails versendet. Das Passwort wird
          verschlüsselt gespeichert.
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-stone-500">SMTP-Server *</label>
            <input
              className="input"
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="mail.example.de"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">Port</label>
            <input
              className="input"
              type="number"
              value={port}
              onChange={(e) => setPort(Number(e.target.value))}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">Sicherheit</label>
            <select className="input" value={security} onChange={(e) => setSecurity(e.target.value)}>
              <option value="starttls">STARTTLS</option>
              <option value="ssl">SSL/TLS</option>
              <option value="none">Keine</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">Benutzername</label>
            <input
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="optional"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">
              Passwort {cfg?.has_password && <span className="text-green-600">(gespeichert)</span>}
            </label>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={cfg?.has_password ? "unverändert lassen" : "optional"}
              autoComplete="new-password"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">Absenderadresse *</label>
            <input
              className="input"
              type="email"
              value={fromAddress}
              onChange={(e) => setFromAddress(e.target.value)}
              placeholder="ich@example.de"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">Absendername</label>
            <input
              className="input"
              value={fromName}
              onChange={(e) => setFromName(e.target.value)}
              placeholder="optional"
            />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button onClick={save} disabled={saving} className="btn-primary text-sm">
            {saving ? "Speichern…" : "Speichern"}
          </button>
          <button onClick={test} disabled={testing || !cfg} className="btn text-sm" title={!cfg ? "Erst speichern" : ""}>
            {testing ? "Sende…" : "Test-Email senden"}
          </button>
          {cfg && (
            <button onClick={remove} className="btn text-sm text-red-600">
              Löschen
            </button>
          )}
        </div>

        {message && (
          <p className={`mt-3 text-sm ${message.ok ? "text-green-600" : "text-red-600"}`}>
            {message.text}
          </p>
        )}
      </section>
    </div>
  );
}
