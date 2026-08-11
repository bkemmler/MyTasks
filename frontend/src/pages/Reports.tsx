import { useEffect, useMemo, useState } from "react";
import { format, parseISO } from "date-fns";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
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

const STATUS_LABEL: Record<Status, string> = {
  offen: "Offen",
  in_bearbeitung: "In Bearbeitung",
  wartend: "Wartend",
  erledigt: "Erledigt",
  abgebrochen: "Abgebrochen",
};

export function Reports() {
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

  const exportCsv = () => {
    window.open(`/api/v1/reports/export?format=csv&${params}`, "_blank");
  };
  const exportJson = () => {
    window.open(`/api/v1/reports/export?format=json&${params}`, "_blank");
  };

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Berichte</h1>

      {stats && (
        <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-5">
          <Stat label="Erstellt" value={stats.created} />
          <Stat label="Erledigt" value={stats.completed} />
          <Stat label="Quote" value={`${Math.round(stats.completion_rate * 100)}%`} />
          <Stat label="Überfällig" value={stats.overdue} accent="red" />
          <Stat
            label="Ø Stunden"
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
            Offen
          </button>
          <button
            onClick={() => setView("completed")}
            className={`px-3 py-1.5 ${view === "completed" ? "bg-blue-600 text-white" : "bg-white dark:bg-stone-800"}`}
          >
            Erledigt
          </button>
        </div>

        <input
          placeholder="🔍 Suchen…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input w-48"
        />

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as Status | "")}
          className="input w-auto"
        >
          <option value="">Alle Status</option>
          {Object.entries(STATUS_LABEL).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>

        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="input w-auto"
        >
          <option value={7}>7 Tage</option>
          <option value={30}>30 Tage</option>
          <option value={90}>90 Tage</option>
          <option value={365}>1 Jahr</option>
        </select>

        <div className="ml-auto flex gap-2">
          <button onClick={exportCsv} className="btn">
            📥 CSV
          </button>
          <button onClick={exportJson} className="btn">
            📥 JSON
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-stone-500">Lade…</p>
      ) : filteredTasks.length === 0 ? (
        <p className="text-stone-500 italic">Keine Aufgaben in diesem Zeitraum.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-stone-300 bg-stone-100 text-left dark:border-stone-700 dark:bg-stone-800">
              <tr>
                <th className="px-2 py-2">Titel</th>
                <th className="px-2 py-2 w-20">Status</th>
                <th className="px-2 py-2 w-16">Prio</th>
                <th className="px-2 py-2 w-40">Fällig</th>
                {view === "completed" && (
                  <th className="px-2 py-2 w-40">Erledigt</th>
                )}
                <th className="px-2 py-2 w-32">Erstellt</th>
              </tr>
            </thead>
            <tbody>
              {filteredTasks.map((t) => (
                <tr
                  key={t.uuid}
                  className="border-b border-stone-100 hover:bg-stone-50 dark:border-stone-800 dark:hover:bg-stone-800"
                >
                  <td className="px-2 py-2">
                    <Link
                      to={`/tasks/${t.uuid}`}
                      className="text-blue-600 hover:underline"
                    >
                      {t.title}
                    </Link>
                  </td>
                  <td className="px-2 py-2">
                    {t.status === "erledigt" ? (
                      <button
                        onClick={() =>
                          updateTask.mutate({
                            uuid: t.uuid,
                            body: { status: "offen", completed_at: null },
                          })
                        }
                        className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700 hover:bg-green-200 dark:bg-green-900 dark:text-green-300"
                      >
                        ↺ Offen
                      </button>
                    ) : (
                      <span className="text-stone-500">{STATUS_LABEL[t.status]}</span>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs ${
                        t.priority === 1
                          ? "bg-red-100 text-red-800"
                          : t.priority === 2
                            ? "bg-orange-100 text-orange-800"
                            : "bg-stone-100 text-stone-600"
                      }`}
                    >
                      P{t.priority}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-stone-500">
                    {t.due_at ? format(parseISO(t.due_at), "dd.MM. HH:mm") : "–"}
                  </td>
                  {view === "completed" && (
                    <td className="px-2 py-2 text-stone-500">
                      {t.completed_at
                        ? format(parseISO(t.completed_at), "dd.MM.yyyy HH:mm")
                        : "–"}
                    </td>
                  )}
                  <td className="px-2 py-2 text-stone-500">
                    {format(parseISO(t.created_at), "dd.MM.yyyy")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-4 text-xs text-stone-500">
        {filteredTasks.length} {filteredTasks.length === 1 ? "Aufgabe" : "Aufgaben"} · Periode: {days}{" "}
        Tage
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
