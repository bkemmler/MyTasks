import { useEffect, useMemo, useState } from "react";
import { format, parseISO } from "date-fns";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, apiRaw } from "../lib/api";
import { useI18n } from "../lib/i18n";
import { useUpdateTask } from "../lib/queries";

type Status = "offen" | "in_bearbeitung" | "wartend" | "erledigt" | "abgebrochen";

interface ReportTask {
  uuid: string;
  title: string;
  description: string | null;
  source_text: string | null;
  status: Status;
  priority: number;
  due_at: string | null;
  completed_at: string | null;
  waiting_for: string | null;
  created_at: string;
  category_id: number | null;
}

interface Stats {
  period_days: number;
  created: number;
  completed: number;
  completion_rate: number;
  overdue: number;
  avg_completion_hours: number | null;
  open_by_priority: Record<number, number>;
  completed_by_category: { category_id: number; count: number }[];
}

export function Reports() {
  const { t } = useI18n();
  const { t: tStatus } = useTranslation();
  const [view, setView] = useState<"open" | "completed">("open");
  const [days, setDays] = useState(30);
  const [statusFilter, setStatusFilter] = useState<Status | "">("");
  const [search, setSearch] = useState("");

  const [tasks, setTasks] = useState<ReportTask[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const updateTask = useUpdateTask();

  const params = useMemo(() => {
    const p = new URLSearchParams();
    if (view === "completed") {
      p.set("status", "erledigt");
      p.set("include_completed", "true");
    } else {
      p.set("include_completed", "true");
    }
    if (statusFilter) p.set("status", statusFilter);
    p.set("limit", "500");
    return p.toString();
  }, [view, statusFilter]);

  const filteredTasks = useMemo(() => {
    if (!search.trim()) return tasks;
    const q = search.toLowerCase();
    return tasks.filter(
      (t) =>
        t.title.toLowerCase().includes(q) ||
        t.description?.toLowerCase().includes(q) ||
        t.source_text?.toLowerCase().includes(q) ||
        t.waiting_for?.toLowerCase().includes(q),
    );
  }, [tasks, search]);

  const reload = async () => {
    setLoading(true);
    try {
      const [taskData, statsData] = await Promise.all([
        api<ReportTask[]>(`/tasks?${params}`),
        api<Stats>(`/reports/stats?days=${days}`),
      ]);
      setTasks(taskData);
      setStats(statsData);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
  }, [params, days]);

  const [exportError, setExportError] = useState<string | null>(null);

  const exportFile = async (fmt: "csv" | "json") => {
    setExportError(null);
    try {
      // window.open() sendet keinen Authorization-Header → Download via
      // fetch mit Token, Antwort als Blob, Download per <a download>.
      const resp = await apiRaw(`/reports/export?format=${fmt}&${params}`);
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `MyTasks-export-${format(new Date(), "yyyyMMdd")}.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setExportError(t("reports.exportFailed", { message: (e as Error).message }));
    }
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">{t("reports.heading")}</h1>

      {stats && (
        <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
          <Stat label={t("reports.statCreated")} value={stats.created} />
          <Stat label={t("reports.statCompleted")} value={stats.completed} />
          <Stat label={t("reports.statRate")} value={`${Math.round(stats.completion_rate * 100)}%`} />
          <Stat label={t("reports.statOverdue")} value={stats.overdue} accent="red" />
          <Stat
            label={t("reports.statAvgHours")}
            value={stats.avg_completion_hours ?? "–"}
          />
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <div className="flex rounded border border-stone-300 dark:border-stone-600">
          <button
            onClick={() => setView("open")}
            className={`px-3 py-1.5 ${view === "open" ? "bg-blue-600 text-white" : "bg-white dark:bg-stone-800"}`}
          >
            {t("reports.tabOpen")}
          </button>
          <button
            onClick={() => setView("completed")}
            className={`px-3 py-1.5 ${view === "completed" ? "bg-blue-600 text-white" : "bg-white dark:bg-stone-800"}`}
          >
            {t("reports.tabCompleted")}
          </button>
        </div>

        <input
          placeholder={t("capture.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input w-48"
        />

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as Status | "")}
          className="input w-auto"
        >
          <option value="">{t("reports.allStatuses")}</option>
          {["offen", "in_bearbeitung", "wartend", "erledigt", "abgebrochen"].map((k) => (
            <option key={k} value={k}>{tStatus(`common.status.${k}`)}</option>
          ))}
        </select>

        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="input w-auto"
        >
          <option value={7}>{t("reports.days7")}</option>
          <option value={30}>{t("reports.days30")}</option>
          <option value={90}>{t("reports.days90")}</option>
          <option value={365}>{t("reports.days365")}</option>
        </select>

        <div className="ml-auto flex gap-2">
          <button onClick={() => exportFile("csv")} className="btn">
            📥 CSV
          </button>
          <button onClick={() => exportFile("json")} className="btn">
            📥 JSON
          </button>
        </div>
      </div>

      {exportError && (
        <p className="mb-2 text-sm text-red-600">{exportError}</p>
      )}

      {loading ? (
        <p className="text-stone-500">{t("common.loading")}</p>
      ) : filteredTasks.length === 0 ? (
        <p className="text-stone-500 italic">{t("reports.noTasksInPeriod")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-stone-300 bg-stone-100 text-left dark:border-stone-700 dark:bg-stone-800">
              <tr>
                <th className="px-2 py-2">{t("reports.thTitle")}</th>
                <th className="px-2 py-2 w-20">{t("reports.thStatus")}</th>
                <th className="px-2 py-2 w-16">{t("reports.thPrio")}</th>
                <th className="px-2 py-2 w-40">{t("reports.thDue")}</th>
                {view === "completed" && (
                  <th className="px-2 py-2 w-40">{t("reports.thCompleted")}</th>
                )}
                <th className="px-2 py-2 w-32">{t("reports.thCreated")}</th>
              </tr>
            </thead>
            <tbody>
              {filteredTasks.map((task) => (
                <tr
                  key={task.uuid}
                  className="border-b border-stone-100 hover:bg-stone-50 dark:border-stone-800 dark:hover:bg-stone-800"
                >
                  <td className="px-2 py-2">
                    <Link
                      to={`/tasks/${task.uuid}`}
                      className="text-blue-600 hover:underline"
                    >
                      {task.title}
                    </Link>
                  </td>
                  <td className="px-2 py-2">
                    {task.status === "erledigt" ? (
                      <button
                        onClick={() =>
                          updateTask.mutate({
                            uuid: task.uuid,
                            body: { status: "offen", completed_at: null },
                          })
                        }
                        className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700 hover:bg-green-200 dark:bg-green-900 dark:text-green-300"
                      >
                        {t("reports.reopen")}
                      </button>
                    ) : (
                      <span className="text-stone-500">{tStatus(`common.status.${task.status}`)}</span>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs ${
                        task.priority === 1
                          ? "bg-red-100 text-red-800"
                          : task.priority === 2
                            ? "bg-orange-100 text-orange-800"
                            : "bg-stone-100 text-stone-600"
                      }`}
                    >
                      P{task.priority}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-stone-500">
                    {task.due_at ? format(parseISO(task.due_at), "dd.MM. HH:mm") : "–"}
                  </td>
                  {view === "completed" && (
                    <td className="px-2 py-2 text-stone-500">
                      {task.completed_at
                        ? format(parseISO(task.completed_at), "dd.MM.yyyy HH:mm")
                        : "–"}
                    </td>
                  )}
                  <td className="px-2 py-2 text-stone-500">
                    {format(parseISO(task.created_at), "dd.MM.yyyy")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-4 text-xs text-stone-500">
        {t(filteredTasks.length === 1 ? "reports.count_one" : "reports.count_other", {
          count: filteredTasks.length,
          days,
        })}
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | string;
  accent?: "red";
}) {
  return (
    <div
      className={`rounded border p-3 ${
        accent === "red" ? "border-red-300 bg-red-50 dark:bg-red-950" : "border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900"
      }`}
    >
      <div className="text-xs text-stone-500">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}
