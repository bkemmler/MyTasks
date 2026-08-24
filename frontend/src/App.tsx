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
        <Route path="/categories" element={<Categories />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/settings" element={<Settings />} />
        {user.is_admin && <Route path="/admin/*" element={<Admin />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
