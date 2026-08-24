import { useEffect, useState } from "react";
import { useI18n } from "../lib/i18n";
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

interface Me {
  username: string;
  email: string | null;
  display_name: string | null;
  timezone: string;
  daily_summary_enabled: boolean;
  daily_summary_time: string;
}

interface LLMConfig {
  ollama_base_url: string;
  ollama_model: string;
  enabled: boolean;
}

const TIMEZONES = [
  "Europe/Berlin",
  "Europe/Vienna",
  "Europe/Zurich",
  "Europe/London",
  "UTC",
];

export function Settings() {
  const { t } = useI18n();
  const [me, setMe] = useState<Me | null>(null);
  const [profileMsg, setProfileMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);

  // Profil-Drafts
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [timezone, setTimezone] = useState("Europe/Berlin");
  const [summaryEnabled, setSummaryEnabled] = useState(false);
  const [summaryTime, setSummaryTime] = useState("07:00");

  useEffect(() => {
    api<Me>("/auth/me").then((m) => {
      setMe(m);
      setEmail(m.email ?? "");
      setDisplayName(m.display_name ?? "");
      setTimezone(m.timezone);
      setSummaryEnabled(m.daily_summary_enabled);
      setSummaryTime(m.daily_summary_time);
    });
  }, []);

  const saveProfile = async () => {
    setSavingProfile(true);
    setProfileMsg(null);
    try {
      await api("/auth/me", {
        method: "PATCH",
        body: JSON.stringify({
          email: email || null,
          display_name: displayName || null,
          timezone,
          daily_summary_enabled: summaryEnabled,
          daily_summary_time: summaryTime,
        }),
      });
      setProfileMsg({ ok: true, text: t("settings.profileSaved") });
    } catch (e) {
      setProfileMsg({ ok: false, text: t("common.error", { message: String(e) }) });
    } finally {
      setSavingProfile(false);
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">{t("settings.heading")}</h2>

      <section className="rounded-lg border border-stone-200 p-4 dark:border-stone-800">
        <h3 className="mb-1 font-semibold">{t("settings.profileHeading")}</h3>
        <p className="mb-4 text-xs text-stone-500">
          {t("settings.loggedInAs")} <strong>{me?.username}</strong>
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-stone-500">{t("settings.displayName")}</label>
            <input
              className="input"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder={t("settings.optional")}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">
              {t("settings.email")}
            </label>
            <input
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="ich@example.de"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">{t("settings.timezone")}</label>
            <select className="input" value={timezone} onChange={(e) => setTimezone(e.target.value)}>
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>{tz}</option>
              ))}
            </select>
          </div>
        </div>

        <h4 className="mt-4 mb-2 text-sm font-medium">{t("settings.summaryHeading")}</h4>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={summaryEnabled}
              onChange={(e) => setSummaryEnabled(e.target.checked)}
            />
            {t("settings.active")}
          </label>
          <div>
            <label className="mb-1 block text-xs text-stone-500">{t("settings.time")}</label>
            <input
              className="input w-28"
              type="time"
              value={summaryTime}
              disabled={!summaryEnabled}
              onChange={(e) => setSummaryTime(e.target.value)}
            />
          </div>
        </div>

        <div className="mt-4">
          <button onClick={saveProfile} disabled={savingProfile} className="btn-primary text-sm">
            {savingProfile ? t("common.saving") : t("common.save")}
          </button>
        </div>
        {profileMsg && (
          <p className={`mt-3 text-sm ${profileMsg.ok ? "text-green-600" : "text-red-600"}`}>
            {profileMsg.text}
          </p>
        )}
      </section>

      <MailSection />
      <LLMSection />
    </div>
  );
}

function LLMSection() {
  const { t } = useI18n();
  const [cfg, setCfg] = useState<LLMConfig | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [baseUrl, setBaseUrl] = useState("http://");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api<LLMConfig>("/auth/me/llm-config")
      .then((res) => {
        setCfg(res);
        setBaseUrl(res.ollama_base_url);
        setModel(res.ollama_model);
      })
      .catch(() => setCfg(null))
      .finally(() => setLoaded(true));
  }, []);

  const testConnection = async () => {
    setTesting(true);
    setMessage(null);
    try {
      const res = await api<{ success: boolean; models: string[]; detail?: string }>(
        "/auth/me/llm-config/test",
        { method: "POST", body: JSON.stringify({ ollama_base_url: baseUrl }) },
      );
      if (res.success) {
        setModels(res.models);
        setMessage({ ok: true, text: t("settings.connOk", { count: res.models.length }) });
      } else {
        setModels([]);
        setMessage({
          ok: false,
          text: t("settings.connFailed", { detail: res.detail ? `: ${res.detail}` : "" }),
        });
      }
    } catch (e) {
      setMessage({ ok: false, text: t("common.error", { message: (e as Error).message }) });
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    if (!baseUrl) {
      setMessage({ ok: false, text: t("settings.baseUrlRequired") });
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const res = await api<LLMConfig>("/auth/me/llm-config", {
        method: "PUT",
        body: JSON.stringify({ ollama_base_url: baseUrl, ollama_model: model }),
      });
      setCfg(res);
      setMessage({
        ok: true,
        text: res.enabled
          ? t("settings.llmSavedActive", { model: res.ollama_model })
          : t("settings.llmSavedInactive"),
      });
    } catch (e) {
      setMessage({ ok: false, text: t("common.error", { message: (e as Error).message }) });
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!confirm(t("settings.llmDeleteConfirm"))) return;
    try {
      await api("/auth/me/llm-config", { method: "DELETE" });
      setCfg(null);
      setModels([]);
      setMessage({ ok: true, text: t("settings.mailDeleted") });
    } catch (e) {
      setMessage({ ok: false, text: t("common.error", { message: (e as Error).message }) });
    }
  };

  if (!loaded) return <div className="text-stone-500">Lade…</div>;

  return (
    <section className="rounded-lg border border-stone-200 p-4 dark:border-stone-800">
      <div className="mb-1 flex items-center justify-between">
        <h3 className="font-semibold">{t("settings.llmHeading")}</h3>
        <span className={`text-xs ${cfg?.enabled ? "text-green-600" : "text-stone-400"}`}>
          {cfg?.enabled ? t("settings.llmActive") : t("settings.llmInactive")}
        </span>
      </div>
      <p className="mb-4 text-xs text-stone-500">
{t("settings.llmHint")}
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-xs text-stone-500">{t("settings.ollamaUrl")}</label>
          <input
            className="input"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://192.168.100.91:11434"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-stone-500">{t("settings.model")}</label>
          {models.length > 0 ? (
            <select className="input" value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="">{t("settings.modelDisabledOption")}</option>
              {models.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          ) : (
            <input
              className="input"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder={t("settings.modelFreeText")}
            />
          )}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button onClick={testConnection} disabled={testing || !baseUrl} className="btn text-sm">
          {testing ? t("settings.checking") : t("settings.testLoadModels")}
        </button>
        <button onClick={save} disabled={saving || !baseUrl} className="btn-primary text-sm">
          {saving ? t("common.saving") : t("common.save")}
        </button>
        {cfg && (
          <button onClick={remove} className="btn text-sm text-red-600">
            {t("common.delete")}
          </button>
        )}
      </div>

      {models.length > 0 && model === "" && (
        <p className="mt-2 text-xs text-stone-500">
          Modell „— deaktiviert —" wählen und speichern, um das LLM auszuschalten.
        </p>
      )}
      {message && (
        <p className={`mt-3 text-sm ${message.ok ? "text-green-600" : "text-red-600"}`}>
          {message.text}
        </p>
      )}
    </section>
  );
}

function MailSection() {
  const { t } = useI18n();
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
      setMessage({ ok: false, text: t("settings.requiredHostSender") });
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
      setMessage({ ok: true, text: t("settings.mailSaved") });
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
          ? { ok: true, text: t("settings.testSentTo", { to: res.to }) }
          : { ok: false, text: t("settings.testFailed", { detail: res.detail ? `: ${res.detail}` : "" }) },
      );
    } catch (e) {
      setMessage({ ok: false, text: `Test fehlgeschlagen: ${e}` });
    } finally {
      setTesting(false);
    }
  };

  const remove = async () => {
    if (!confirm(t("settings.mailDeleteConfirm"))) return;
    try {
      await api("/auth/me/mail-config", { method: "DELETE" });
      setCfg(null);
      setHost("");
      setUsername("");
      setPassword("");
      setFromAddress("");
      setFromName("");
      setMessage({ ok: true, text: t("settings.mailDeleted") });
    } catch (e) {
      setMessage({ ok: false, text: `Löschen fehlgeschlagen: ${e}` });
    }
  };

  if (!loaded) return <div className="text-stone-500">Lade…</div>;

  return (
    <section className="rounded-lg border border-stone-200 p-4 dark:border-stone-800">
      <div className="mb-1 flex items-center justify-between">
        <h3 className="font-semibold">{t("settings.mailHeading")}</h3>
        <span
          className={`text-xs ${cfg ? "text-green-600" : "text-stone-400"}`}
        >
          {cfg ? t("settings.mailConfigured") : t("settings.mailNotConfigured")}
        </span>
      </div>
        <p className="mb-4 text-xs text-stone-500">
{t("settings.mailHint")}
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-stone-500">{t("settings.smtpHost")}</label>
            <input
              className="input"
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="mail.example.de"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">{t("settings.port")}</label>
            <input
              className="input"
              type="number"
              value={port}
              onChange={(e) => setPort(Number(e.target.value))}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">{t("settings.security")}</label>
            <select className="input" value={security} onChange={(e) => setSecurity(e.target.value)}>
              <option value="starttls">{t("settings.secStarttls")}</option>
              <option value="ssl">{t("settings.secSsl")}</option>
              <option value="none">{t("settings.secNone")}</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">{t("settings.smtpUsername")}</label>
            <input
              className="input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t("settings.optional")}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">
              {t("settings.smtpPassword")} {cfg?.has_password && <span className="text-green-600">{t("settings.passwordStored")}</span>}
            </label>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={cfg?.has_password ? t("settings.passwordKeep") : t("settings.optional")}
              autoComplete="new-password"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">{t("settings.fromAddress")}</label>
            <input
              className="input"
              type="email"
              value={fromAddress}
              onChange={(e) => setFromAddress(e.target.value)}
              placeholder="ich@example.de"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-stone-500">{t("settings.fromName")}</label>
            <input
              className="input"
              value={fromName}
              onChange={(e) => setFromName(e.target.value)}
              placeholder={t("settings.optional")}
            />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button onClick={save} disabled={saving} className="btn-primary text-sm">
            {saving ? t("common.saving") : t("common.save")}
          </button>
          <button onClick={test} disabled={testing || !cfg} className="btn text-sm" title={!cfg ? t("settings.firstSave") : ""}>
            {testing ? t("settings.sending") : t("settings.testSend")}
          </button>
          {cfg && (
            <button onClick={remove} className="btn text-sm text-red-600">
              {t("common.delete")}
            </button>
          )}
        </div>

        {message && (
          <p className={`mt-3 text-sm ${message.ok ? "text-green-600" : "text-red-600"}`}>
            {message.text}
          </p>
        )}
    </section>
  );
}
