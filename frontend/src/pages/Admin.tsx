import { useState, type FormEvent } from "react";
import { useI18n } from "../lib/i18n";
import { NavLink, Route, Routes } from "react-router-dom";
import { api } from "../lib/api";
import { useCreateUser, useDeleteUser, useHealth, useUpdateUser, useUsers, type AdminUser } from "../lib/queries";

export function Admin() {
  const { t } = useI18n();
  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">{t("admin.heading")}</h1>
      <nav className="mb-4 flex gap-1 border-b border-stone-200 dark:border-stone-800">
        <NavLink end to="/admin" className={({ isActive }) => `tab ${isActive ? "tab-active" : ""}`}>
          {t("admin.tabUsers")}
        </NavLink>
        <NavLink to="/admin/system" className={({ isActive }) => `tab ${isActive ? "tab-active" : ""}`}>
          {t("admin.tabSystem")}
        </NavLink>
        <NavLink
          to="/admin/email"
          className={({ isActive }) =>
            `tab ${isActive ? "tab-active" : ""}`
          }
        >
          {t("admin.tabEmail")}
        </NavLink>
      </nav>
      <Routes>
        <Route index element={<Users />} />
        <Route path="system" element={<System />} />
        <Route path="email" element={<EmailSettings />} />
      </Routes>
    </div>
  );
}

function Users() {
  const { t } = useI18n();
  const { data, isLoading } = useUsers();
  const create = useCreateUser();
  const update = useUpdateUser();
  const del = useDeleteUser();

  const [form, setForm] = useState({
    username: "",
    password: "",
    display_name: "",
    is_admin: false,
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.username || !form.password) return;
    create.mutate(form, {
      onSuccess: () =>
        setForm({ username: "", password: "", display_name: "", is_admin: false }),
    });
  }

  if (isLoading) return <p>{t("common.loading")}</p>;

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className="space-y-2 rounded border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
        <h2 className="font-medium">{t("admin.newUser")}</h2>
        <div className="grid gap-2 sm:grid-cols-2">
          <input
            placeholder={t("admin.phUsername")}
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            className="input"
          />
          <input
            type="password"
            placeholder={t("admin.phPassword")}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="input"
          />
          <input
            placeholder={t("admin.phDisplayName")}
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            className="input"
          />
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.is_admin}
              onChange={(e) => setForm({ ...form, is_admin: e.target.checked })}
            />
            <span>{t("admin.isAdmin")}</span>
          </label>
        </div>
        <button type="submit" className="btn-primary" disabled={create.isPending}>
          {t("admin.create")}
        </button>
      </form>

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-stone-200 text-left dark:border-stone-800">
            <th className="py-2">{t("admin.thUsername")}</th>
            <th>{t("admin.thName")}</th>
            <th>{t("admin.thRole")}</th>
            <th>{t("admin.thStatus")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data?.map((u) => (
            <UserRow
              key={u.id}
              user={u}
              onToggleAdmin={() =>
                update.mutate({ id: u.id, body: { is_admin: !u.is_admin } })
              }
              onToggleActive={() =>
                update.mutate({ id: u.id, body: { is_active: !u.is_active } })
              }
              onDelete={(hard) => {
                if (confirm(t("admin.deleteConfirm", { name: u.username }))) {
                  del.mutate({ id: u.id, hard });
                }
              }}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UserRow({
  user,
  onToggleAdmin,
  onToggleActive,
  onDelete,
}: {
  user: AdminUser;
  onToggleAdmin: () => void;
  onToggleActive: () => void;
  onDelete: (hard: boolean) => void;
}) {
  const { t } = useI18n();
  return (
    <tr className="border-b border-stone-100 dark:border-stone-800">
      <td className="py-2 font-mono">{user.username}</td>
      <td>{user.display_name ?? "—"}</td>
      <td>
        <button
          onClick={onToggleAdmin}
          className={`rounded px-1.5 py-0.5 text-xs ${user.is_admin ? "bg-blue-100 text-blue-800" : "bg-stone-100"}`}
        >
          {user.is_admin ? t("admin.roleAdmin") : t("admin.roleUser")}
        </button>
      </td>
      <td>
        <button
          onClick={onToggleActive}
          className={`rounded px-1.5 py-0.5 text-xs ${user.is_active ? "bg-green-100 text-green-800" : "bg-stone-200 text-stone-600"}`}
        >
          {user.is_active ? t("admin.active") : t("admin.inactive")}
        </button>
      </td>
      <td className="text-right">
        <button onClick={() => onDelete(false)} className="btn text-xs">
          {t("admin.deactivate")}
        </button>
        <button onClick={() => onDelete(true)} className="btn text-xs text-red-600">
          {t("admin.hardDelete")}
        </button>
      </td>
    </tr>
  );
}

function System() {
  const { t } = useI18n();
  const { data: health } = useHealth();
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-medium">{t("admin.systemHeading")}</h2>
      <dl className="grid grid-cols-2 gap-2 rounded border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
        <dt className="text-stone-500">{t("admin.dtStatus")}</dt>
        <dd>{health?.status ?? "?"}</dd>
        <dt className="text-stone-500">{t("admin.dtVersion")}</dt>
        <dd>{health?.version ?? "?"}</dd>
        <dt className="text-stone-500">{t("admin.dtUptime")}</dt>
        <dd>{health ? `${Math.round(health.uptime_seconds)}s` : "?"}</dd>
        <dt className="text-stone-500">Ollama</dt>
        <dd>
          <span
            className={
              health?.ollama === "ok"
                ? "text-green-600"
                : health?.ollama === "error"
                  ? "text-red-600"
                  : health?.ollama === "disabled"
                    ? "text-stone-400"
                    : "text-stone-500"
            }
          >
            {health?.ollama ?? "?"}
          </span>
        </dd>
      </dl>
      <p className="text-xs text-stone-500">
        LLM-Konfiguration und Prompt-Verwaltung werden in Phase 4 ergänzt.
      </p>
    </div>
  );
}

function EmailSettings() {
  const { t } = useI18n();
  const [testAddress, setTestAddress] = useState("");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sendResult, setSendResult] = useState<string | null>(null);

  async function sendTest() {
    if (!testAddress) return;
    setTesting(true);
    setTestResult(null);
    try {
      const r = await api<{ success: boolean; to: string }>("/admin/smtp/test", {
        method: "POST",
        body: JSON.stringify({ to_address: testAddress }),
      });
      setTestResult(
        r.success
          ? t("admin.testOk", { to: r.to })
          : t("admin.testFail")
      );
    } catch (e) {
      setTestResult(`❌ Fehler: ${(e as Error).message}`);
    } finally {
      setTesting(false);
    }
  }

  async function sendSummary() {
    setSending(true);
    setSendResult(null);
    try {
      const r = await api<{ sent: number; total?: number; user_id?: number }>(
        "/admin/summary/send",
        { method: "POST", body: JSON.stringify({}) }
      );
      if (r.total !== undefined) {
        setSendResult(`✅ ${r.sent}/${r.total} Zusammenfassungen versendet`);
      } else {
        setSendResult(
          r.sent > 0
            ? `✅ Zusammenfassung an user_id=${r.user_id} versendet`
            : `⚠ Versand übersprungen (kein SMTP / kein E-Mail-Empfänger)`
        );
      }
    } catch (e) {
      setSendResult(`❌ Fehler: ${(e as Error).message}`);
    } finally {
      setSending(false);
    }
  }

  async function previewSummary() {
    const r = await api<{ html: string; text: string }>("/admin/summary/preview", {
      method: "POST",
      body: JSON.stringify({}),
    });
    const win = window.open("", "_blank");
    if (win) win.document.write(r.html);
  }

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-medium">{t("admin.emailHeading")}</h2>

      <section className="space-y-3 rounded border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
        <h3 className="text-sm font-medium">{t("admin.testSendHeading")}</h3>
        <p className="text-xs text-stone-500">
{t("admin.testSendHint")}
        </p>
        <div className="flex gap-2">
          <input
            type="email"
            placeholder={t("admin.phRecipient")}
            value={testAddress}
            onChange={(e) => setTestAddress(e.target.value)}
            className="input flex-1"
          />
          <button onClick={sendTest} disabled={!testAddress || testing} className="btn-primary">
            {testing ? t("settings.sending") : t("admin.sendTest")}
          </button>
        </div>
        {testResult && <p className="text-sm">{testResult}</p>}
      </section>

      <section className="space-y-3 rounded border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900">
        <h3 className="text-sm font-medium">{t("admin.summaryHeading")}</h3>
        <p className="text-xs text-stone-500">
{t("admin.summaryHint")}
        </p>
        <div className="flex gap-2">
          <button onClick={sendSummary} disabled={sending} className="btn-primary">
            {sending ? t("settings.sending") : t("admin.sendAllNow")}
          </button>
          <button onClick={previewSummary} className="btn">
            {t("admin.preview")}
          </button>
        </div>
        {sendResult && <p className="text-sm">{sendResult}</p>}
      </section>
    </div>
  );
}
