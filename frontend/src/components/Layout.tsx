import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useHealth, useVersion } from "../lib/queries";
import { useI18n } from "../lib/i18n";
import { CaptureInput } from "./CaptureInput";
import { useSSE } from "../lib/sse";

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { t, setLanguage, lang } = useI18n();
  const { t: _t } = useTranslation();
  const { data: health } = useHealth();
  const { data: version } = useVersion();
  const navigate = useNavigate();
  const location = useLocation();
  const [showCapture, setShowCapture] = useState(false);
  useSSE();

  // Aktueller Task-View aus der URL (z. B. /tasks/today → "today")
  const currentView = location.pathname.match(/^\/tasks\/([\w-]+)/)?.[1] ?? "";
  // Umschalter zeigen immer das jeweils andere Ziel
  const isToday = currentView === "today";
  const isWeek = currentView === "week";

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key === "k") {
        e.preventDefault();
        setShowCapture((s) => !s);
      } else if (e.key === "Escape") {
        setShowCapture(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="min-h-screen">
      <header className="border-b border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-950">
        <div className="mx-auto flex max-w-5xl items-center gap-x-4 px-3 py-2 sm:px-4">
          <Link to="/" className="shrink-0 text-lg font-bold">
            MyTasks
          </Link>
          <nav className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
            {/* Umschalter Heute/Morgen: zeigt das jeweils andere Ziel */}
            <Link to={isToday ? "/tasks/tomorrow" : "/tasks/today"} className="tab whitespace-nowrap">
              {isToday ? t("nav.tomorrow") : t("nav.today")}
            </Link>
            {/* Umschalter Woche/Nächste */}
            <Link to={isWeek ? "/tasks/next-week" : "/tasks/week"} className="tab whitespace-nowrap">
              {isWeek ? t("nav.next") : t("nav.week")}
            </Link>
            <NavLink
              to="/tasks/inbox"
              className={({ isActive }) =>
                `tab ${isActive ? "tab-active" : ""}`
              }
            >
              {t("nav.inbox")}
            </NavLink>
            <NavLink
              to="/tasks/review"
              className={({ isActive }) =>
                `tab ${isActive ? "tab-active" : ""}`
              }
            >
              ⚠
            </NavLink>
            <NavLink
              to="/tasks/all"
              className={({ isActive }) =>
                `tab ${isActive ? "tab-active" : ""}`
              }
            >
              {t("nav.all")}
            </NavLink>
            <NavLink
              to="/categories"
              className={({ isActive }) =>
                `tab ${isActive ? "tab-active" : ""}`
              }
            >
              {t("nav.categories")}
            </NavLink>
            <NavLink
              to="/reports"
              className={({ isActive }) =>
                `tab ${isActive ? "tab-active" : ""}`
              }
            >
              {t("nav.reports")}
            </NavLink>
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                `tab ${isActive ? "tab-active" : ""}`
              }
            >
              {t("nav.settings")}
            </NavLink>
            {user?.is_admin && (
              <NavLink
                to="/admin"
                className={({ isActive }) =>
                  `tab ${isActive ? "tab-active" : ""}`
                }
              >
                Admin
              </NavLink>
            )}
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-2 text-sm sm:gap-3">
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${
                health?.ollama === "ok"
                  ? "bg-green-500"
                  : health?.ollama === "error"
                    ? "bg-red-500"
                    : health?.ollama === "disabled"
                      ? "bg-stone-300"
                      : "bg-sky-400"
              }`}
              title={
                health?.ollama === "per-user"
                  ? t("nav.llmPerUser")
                  : `Ollama: ${health?.ollama ?? "?"}`
              }
            />
            <span className="hidden text-stone-500 sm:inline">{user?.display_name || user?.username}</span>
            <span className="hidden rounded bg-stone-100 px-1.5 py-0.5 font-mono text-xs text-stone-500 dark:bg-stone-800 dark:text-stone-400 md:inline">
              v{version?.app ?? "?"}
            </span>
            <div className="flex overflow-hidden rounded border border-stone-300 text-xs dark:border-stone-600">
              <button
                onClick={() => setLanguage("de")}
                className={`px-2 py-0.5 ${lang === "de" ? "bg-stone-700 text-white" : "hover:bg-stone-100 dark:hover:bg-stone-800"}`}
              >
                DE
              </button>
              <button
                onClick={() => setLanguage("en")}
                className={`px-2 py-0.5 ${lang === "en" ? "bg-stone-700 text-white" : "hover:bg-stone-100 dark:hover:bg-stone-800"}`}
              >
                EN
              </button>
            </div>
            <button
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
              className="btn"
            >
              {t("nav.logout")}
            </button>
          </div>
        </div>
      </header>

      {showCapture && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-24"
          onClick={() => setShowCapture(false)}
        >
          <div
            className="w-full max-w-2xl rounded bg-white p-4 shadow-xl dark:bg-stone-900"
            onClick={(e) => e.stopPropagation()}
          >
            <CaptureInput
              autoFocus
              onDone={() => setShowCapture(false)}
              placeholder={t("capture.modalPlaceholder")}
            />
            <p className="mt-2 text-xs text-stone-500">
              {t("capture.modalHint")}
            </p>
          </div>
        </div>
      )}

      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
    </div>
  );
}
