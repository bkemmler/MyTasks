import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { Tasks } from "./pages/Tasks";
import { Categories } from "./pages/Categories";
import { Reports } from "./pages/Reports";
import { Settings } from "./pages/Settings";
import { Admin } from "./pages/Admin";
import { useTranslation } from "react-i18next";
import { useAuth } from "./lib/auth";

export function App() {
  const { user, isLoading } = useAuth();
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center text-stone-500">
        {t("common.loading")}
      </div>
    );
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Tasks />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/tasks/:view" element={<Tasks />} />
        {/* Legacy-Redirects: alte deutsche View-Pfade → englische URLs */}
        <Route path="/tasks/heute" element={<Navigate to="/tasks/today" replace />} />
        <Route path="/tasks/morgen" element={<Navigate to="/tasks/tomorrow" replace />} />
        <Route path="/tasks/woche" element={<Navigate to="/tasks/week" replace />} />
        <Route path="/tasks/naechste_woche" element={<Navigate to="/tasks/next-week" replace />} />
        <Route path="/tasks/ueberfaellig" element={<Navigate to="/tasks/overdue" replace />} />
        <Route path="/tasks/eingang" element={<Navigate to="/tasks/inbox" replace />} />
        <Route path="/tasks/pruefung" element={<Navigate to="/tasks/review" replace />} />
        <Route path="/tasks/alle" element={<Navigate to="/tasks/all" replace />} />
        <Route path="/tasks/erledigt" element={<Navigate to="/tasks/completed" replace />} />
        <Route path="/categories" element={<Categories />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/settings" element={<Settings />} />
        {user.is_admin && <Route path="/admin/*" element={<Admin />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
