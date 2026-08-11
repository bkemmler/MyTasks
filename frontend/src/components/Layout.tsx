import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { useHealth, useVersion } from "../lib/queries";
import { CaptureInput } from "./CaptureInput";
import { useSSE } from "../lib/sse";

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { data: health } = useHealth();
  const { data: version } = useVersion();
  const navigate = useNavigate();
  const [showCapture, setShowCapture] = useState(false);
  useSSE();

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
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-1 px-3 py-2 sm:px-4 sm:py-3">
          <Link to="/" className="text-lg font-bold">
            MyTasks
          </Link>
          <nav className="flex gap-1 overflow-x-auto pb-1 sm:pb-0">
            <NavLink
              to="/tasks/heute"
              className={({ isActive }) =>
                `tab whitespace-nowrap ${isActive ? "tab-active" : ""}`
              }
            >
              Heute
            </NavLink>
            <NavLink
              to="/tasks/morgen"
              className={({ isActive }) =>
                `tab whitespace-nowrap ${isActive ? "tab-active" : ""}`
              }
            >
              Morgen
            </NavLink>
            <NavLink
              to="/tasks/woche"
              className={({ isActive }) =>
                `tab whitespace-nowrap ${isActive ? "tab-active" : ""}`
              }
            >
              Woche
            </NavLink>
            <NavLink
              to="/tasks/naechste_woche"
              className={({ isActive }) =>
                `tab whitespace-nowrap ${isActive ? "tab-active" : ""}`
              }
            >
              Nächste
            </NavLink>
            <NavLink
              to="/tasks/eingang"
              className={({ isActive }) =>
                `tab ${isActive ? "tab-active" : ""}`
              }
            >
              Eingang
            </NavLink>
            <NavLink
              to="/tasks/pruefung"
              className={({ isActive }) =>
                `tab ${isActive ? "tab-active" : ""}`
              }
            >
              ⚠
            </NavLink>
            <NavLink
              to="/tasks/alle"
              className={({ isActive }) =>
                `tab ${isActive ? "tab-active" : ""}`
              }
            >
              Alle
            </NavLink>
            <NavLink
              to="/categories"
              className={({ isActive }) =>
                `tab ${isActive ? "tab-active" : ""}`
              }
            >
              Kategorien
            </NavLink>
            <NavLink
              to="/reports"
              className={({ isActive }) =>
                `tab ${isActive ? "tab-active" : ""}`
              }
            >
              Berichte
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
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span
              className={`h-2 w-2 rounded-full ${
                health?.ollama === "ok"
                  ? "bg-green-500"
                  : health?.ollama === "error"
                    ? "bg-red-500"
                    : health?.ollama === "disabled"
                      ? "bg-stone-300"
                      : "bg-stone-400"
              }`}
              title={`Ollama: ${health?.ollama ?? "?"}`}
            />
            <span className="text-stone-500">{user?.display_name || user?.username}</span>
            <span className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-xs text-stone-500 dark:bg-stone-800 dark:text-stone-400">
              v{version?.app ?? "?"}
            </span>
            <button
              onClick={async () => {
                await logout();
                navigate("/login");
              }}
              className="btn"
            >
              Abmelden
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
              placeholder="Was ist zu tun?"
            />
            <p className="mt-2 text-xs text-stone-500">
              Enter zum Erfassen · Esc zum Schließen
            </p>
          </div>
        </div>
      )}

      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
    </div>
  );
}
