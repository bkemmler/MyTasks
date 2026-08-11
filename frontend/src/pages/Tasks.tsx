import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  addDays,
  endOfWeek,
  format,
  isPast,
  isSameDay,
  isThisWeek,
  isToday,
  parseISO,
  startOfDay,
  startOfWeek,
} from "date-fns";
import { de } from "date-fns/locale";
import clsx from "clsx";
import { CaptureInput } from "../components/CaptureInput";
import { TaskRow } from "../components/TaskRow";
import { useCategories, useTasks } from "../lib/queries";
import type { Status } from "../lib/queries";

type View =
  | "heute"
  | "morgen"
  | "woche"
  | "naechste_woche"
  | "ueberfaellig"
  | "eingang"
  | "pruefung"
  | "alle"
  | "erledigt";

const VIEW_TITLES: Record<View, string> = {
  heute: "Heute",
  morgen: "Morgen",
  woche: "Diese Woche",
  naechste_woche: "Nächste Woche",
  ueberfaellig: "Überfällig",
  eingang: "Eingang",
  pruefung: "Zur Prüfung",
  alle: "Alle offenen",
  erledigt: "Erledigt",
};

const isInRange = (d: Date, start: Date, end: Date): boolean => d >= start && d <= end;

export function Tasks() {
  const params = useParams<{ view?: string }>();
  const view = (params.view ?? "heute") as View;
  const [statusFilter, setStatusFilter] = useState<Status | "">("");
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [priority, setPriority] = useState<number | "">("");
  const [showCompleted, setShowCompleted] = useState(false);
  const [showUndated, setShowUndated] = useState(() => {
    try {
      return localStorage.getItem("tasky.show-undated") === "true";
    } catch {
      return true;
    }
  });
  const [sortBy, setSortBy] = useState<"due_at" | "priority" | "created_at" | "title">("due_at");
  const [search, setSearch] = useState("");
  const { data: categories } = useCategories();

  useEffect(() => {
    try {
      localStorage.setItem("tasky.show-undated", String(showUndated));
    } catch {
      // ignore
    }
  }, [showUndated]);

  const [recentlyCompleted, setRecentlyCompleted] = useState<Set<string>>(new Set());

  const onCompleted = useCallback((uuid: string) => {
    setRecentlyCompleted((prev) => new Set(prev).add(uuid));
    setTimeout(() => {
      setRecentlyCompleted((prev) => {
        const next = new Set(prev);
        next.delete(uuid);
        return next;
      });
    }, 4000);
  }, []);

  const filterParams: Record<string, unknown> = useMemo(() => {
    const p: Record<string, unknown> = { include_completed: showCompleted };
    if (statusFilter) p.status = statusFilter;
    if (categoryId !== "") p.category_id = categoryId;
    if (priority !== "") p.priority = priority;
    if (view === "pruefung") p.needs_review = true;
    if (view === "erledigt") {
      p.status = "erledigt";
      p.include_completed = true;
    }
    return p;
  }, [view, statusFilter, categoryId, priority, showCompleted]);

  const { data: tasks, isLoading } = useTasks(view, filterParams);

  const filtered = useMemo(() => {
    if (!tasks) return [];
    const now = new Date();
    const todayStart = startOfDay(now);
    const tomorrowStart = addDays(todayStart, 1);
    const tomorrowEnd = addDays(todayStart, 2);
    const thisWeekStart = startOfWeek(now, { weekStartsOn: 1 });
    const thisWeekEnd = endOfWeek(now, { weekStartsOn: 1 });
    const nextWeekStart = addDays(thisWeekStart, 7);
    const nextWeekEnd = addDays(thisWeekEnd, 7);

    return tasks.filter((t) => {
      const isOpen = t.status !== "erledigt" && t.status !== "abgebrochen";
      if (!isOpen && view !== "erledigt" && !showCompleted && !recentlyCompleted.has(t.uuid)) return false;

      const due = t.due_at ? parseISO(t.due_at) : null;
      const start = t.start_at ? parseISO(t.start_at) : null;

      // Tasks ohne Fälligkeitsdatum in jeder Ansicht zeigen,
      // wenn der Nutzer "Ohne Fälligkeit" aktiviert hat.
      if (showUndated && !due && !start) return true;

      if (view === "heute") {
        if (due && (isToday(due) || isPast(due))) return true;
        if (start && start <= now) return true;
        return false;
      }
      if (view === "morgen") {
        if (due && isInRange(due, tomorrowStart, tomorrowEnd)) return true;
        return false;
      }
      if (view === "woche") {
        if (due && isInRange(due, thisWeekStart, thisWeekEnd)) return true;
        return false;
      }
      if (view === "naechste_woche") {
        if (due && isInRange(due, nextWeekStart, nextWeekEnd)) return true;
        return false;
      }
      if (view === "ueberfaellig") {
        return due !== null && isPast(due);
      }
      if (view === "eingang") {
        return !due && t.status !== "erledigt" && t.status !== "abgebrochen";
      }
      return true;
    }).filter((t) => {
      if (categoryId !== "" && t.category_id !== categoryId) return false;
      return true;
    }).filter((t) => {
      if (!search.trim()) return true;
      const q = search.toLowerCase();
      if (t.title.toLowerCase().includes(q)) return true;
      if (t.description?.toLowerCase().includes(q)) return true;
      if (t.source_text?.toLowerCase().includes(q)) return true;
      if (t.waiting_for?.toLowerCase().includes(q)) return true;
      return false;
    }).sort((a, b) => {
      if (view === "eingang") {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
      if (sortBy === "priority") return a.priority - b.priority;
      if (sortBy === "created_at") return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      if (sortBy === "title") return a.title.localeCompare(b.title);
      // due_at: nulls last, ascending
      if (!a.due_at && !b.due_at) return 0;
      if (!a.due_at) return 1;
      if (!b.due_at) return -1;
      return new Date(a.due_at).getTime() - new Date(b.due_at).getTime();
    });
  }, [tasks, view, categoryId, sortBy, showUndated, showCompleted, recentlyCompleted, search]);

  const categoryCounts = useMemo(() => {
    if (!tasks || !categories) return {};
    const counts: Record<number, number> = {};
    for (const t of tasks) {
      if (t.status === "erledigt" || t.status === "abgebrochen") continue;
      if (t.category_id != null) {
        counts[t.category_id] = (counts[t.category_id] || 0) + 1;
      }
    }
    return counts;
  }, [tasks, categories]);

  return (
    <div>
      <div className="mb-4">
        <CaptureInput
          placeholder="Neue Aufgabe erfassen…"
          viewTitle={VIEW_TITLES[view]}
          taskCount={filtered.length}
        />
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <div className="flex flex-wrap gap-2">
          <input
            type="text"
            placeholder="🔍 Suchen…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input w-36 sm:w-48"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as Status | "")}
            className="input w-auto"
          >
            <option value="">Status: alle</option>
            <option value="offen">Offen</option>
            <option value="in_bearbeitung">In Bearbeitung</option>
            <option value="wartend">Wartend</option>
            <option value="erledigt">Erledigt</option>
          </select>
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value ? Number(e.target.value) : "")}
            className="input w-auto"
          >
            <option value="">Prio: alle</option>
            <option value="1">P1</option>
            <option value="2">P2</option>
            <option value="3">P3</option>
            <option value="4">P4</option>
          </select>
          <select
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : "")}
            className="input w-auto max-w-[160px]"
          >
            <option value="">Kategorie: alle</option>
            {categories?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
            className="input w-auto"
          >
            <option value="due_at">Sort: Fälligkeit ↑</option>
            <option value="priority">Sort: Priorität</option>
            <option value="created_at">Sort: Erstelldatum ↓</option>
            <option value="title">Sort: Titel</option>
          </select>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={showUndated}
              onChange={(e) => setShowUndated(e.target.checked)}
            />
            <span>Ohne Fälligkeit</span>
          </label>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={showCompleted}
              onChange={(e) => setShowCompleted(e.target.checked)}
            />
            <span>Erledigte</span>
          </label>
        </div>
      </div>

      {categories && categories.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1">
          {categories.map((c) => {
            const count = categoryCounts[c.id] || 0;
            const isActive = categoryId === c.id;
            return (
              <button
                key={c.id}
                onClick={() => setCategoryId(isActive ? "" : c.id)}
                className={`rounded-full px-2.5 py-0.5 text-xs transition ${
                  isActive
                    ? "text-white"
                    : "border border-stone-300 text-stone-600 hover:bg-stone-100 dark:border-stone-600 dark:text-stone-300 dark:hover:bg-stone-800"
                }`}
                style={
                  isActive && c.color
                    ? { backgroundColor: c.color }
                    : undefined
                }
              >
                {c.name}
                {count > 0 && (
                  <span className={`ml-1 ${isActive ? "opacity-80" : "text-stone-400"}`}>
                    ({count})
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {isLoading ? (
        <p className="text-stone-500">Lade…</p>
      ) : filtered.length === 0 ? (
        <p className="text-stone-500 italic">Keine Aufgaben.</p>
      ) : (
        <ul className="space-y-1">
          {filtered.map((t) => (
            <TaskRow key={t.uuid} task={t} onCompleted={onCompleted} />
          ))}
        </ul>
      )}

      <p className="mt-6 text-xs text-stone-500">
        Tastatur: <kbd>⌘K</kbd> Capture · <kbd>x</kbd> erledigen · <kbd>1</kbd>-<kbd>4</kbd> Prio
      </p>
    </div>
  );
}

export function dueLabel(dueAt: string | null): string | null {
  if (!dueAt) return null;
  const d = parseISO(dueAt);
  const now = new Date();
  const today = startOfDay(now);
  if (isSameDay(d, today)) return `heute ${format(d, "HH:mm")}`;
  if (isSameDay(d, addDays(today, 1))) return `morgen ${format(d, "HH:mm")}`;
  if (isPast(d)) return `${format(d, "dd.MM. HH:mm")} überfällig`;
  if (isThisWeek(d, { weekStartsOn: 1 })) return format(d, "EEE dd.MM. HH:mm", { locale: de });
  return format(d, "dd.MM.yyyy HH:mm");
}
