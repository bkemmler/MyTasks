import { useState, useEffect, useRef } from "react";
import clsx from "clsx";
import { format, parseISO } from "date-fns";
import { de } from "date-fns/locale";
import { useCategories, useCompleteTask, useConfirmReview, useDeleteTask, useReparse, useUpdateTask, type Task } from "../lib/queries";
import { dueLabel } from "../pages/Tasks";

const PRIO_COLOR: Record<number, string> = {
  1: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  2: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
  3: "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300",
  4: "bg-stone-100 text-stone-500 dark:bg-stone-800 dark:text-stone-400",
};

const STATUS_LABEL: Record<string, string> = {
  offen: "Offen",
  in_bearbeitung: "In Bearbeitung",
  wartend: "Wartend",
  erledigt: "Erledigt",
  abgebrochen: "Abgebrochen",
};

export function TaskRow({ task, onCompleted }: { task: Task; onCompleted?: (uuid: string) => void }) {
  const update = useUpdateTask();
  const complete = useCompleteTask();
  const confirmReview = useConfirmReview();
  const reparse = useReparse();
  const del = useDeleteTask();
  const { data: categories } = useCategories();
  const [editing, setEditing] = useState<string | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [justCompleted, setJustCompleted] = useState(false);

  // Nach dem Abhaken 4s lang "Rückgängig" anzeigen, dann verschwindet die Zeile
  useEffect(() => {
    if (!justCompleted) return;
    const t = setTimeout(() => setJustCompleted(false), 4000);
    return () => clearTimeout(t);
  }, [justCompleted]);

  async function patch(body: Partial<Task>) {
    return update.mutateAsync({ uuid: task.uuid, body });
  }

  const category = categories?.find((c) => c.id === task.category_id);
  const isPending = task.llm_state === "pending";
  const catColor = category?.color || null;

  return (
    <li
      className={clsx(
        "rounded border bg-white px-3 py-2 dark:bg-stone-900",
        task.needs_review
          ? "border-yellow-400 dark:border-yellow-600"
          : "border-stone-200 dark:border-stone-800",
      )}
      style={
        catColor
          ? { borderLeft: `4px solid ${catColor}` }
          : undefined
      }
    >
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={task.status === "erledigt"}
          onChange={() => {
            if (task.status === "erledigt") {
              patch({ status: "offen", completed_at: null });
            } else {
              onCompleted?.(task.uuid);
              setJustCompleted(true);
              complete.mutate(task.uuid);
            }
          }}
          className="mt-1.5 h-4 w-4 cursor-pointer"
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <button
              onClick={() => setShowDetail((s) => !s)}
              className={clsx(
                "flex-1 cursor-pointer text-left hover:underline",
                task.status === "erledigt" && "text-stone-400 line-through",
              )}
              title="Details anzeigen"
            >
              {task.title}
            </button>
            <span
              className={clsx("rounded px-1.5 py-0.5 text-xs", PRIO_COLOR[task.priority])}
              title={`Priorität ${task.priority}`}
            >
              P{task.priority}
            </span>
            {justCompleted && (
              <button
                onClick={() => {
                  patch({ status: "offen", completed_at: null });
                  setJustCompleted(false);
                }}
                className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700 hover:bg-green-200 dark:bg-green-900 dark:text-green-300"
              >
                ✓ Erledigt — Rückgängig
              </button>
            )}
            {task.recurrence_rule && (
              <span
                className="rounded bg-violet-100 px-1.5 py-0.5 text-xs text-violet-700 dark:bg-violet-900 dark:text-violet-300"
                title={`Wiederholung: ${rruleLabel(task.recurrence_rule)}`}
              >
                ↻
              </span>
            )}
            {task.needs_review && (
              <button
                onClick={() => confirmReview.mutate(task.uuid)}
                className="rounded bg-yellow-100 px-1.5 py-0.5 text-xs text-yellow-800 hover:bg-yellow-200 dark:bg-yellow-900 dark:text-yellow-200"
                title={task.review_notes || "Bitte prüfen"}
              >
                ⚠ prüfen
              </button>
            )}
            {isPending && (
              <span
                className="rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                title="LLM verarbeitet…"
              >
                ✦
              </span>
            )}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-3 text-xs text-stone-500">
            {task.due_at && <span>{dueLabel(task.due_at)}</span>}
            {task.original_due_at && task.due_at !== task.original_due_at && (
              <span className="text-stone-400 line-through" title={`Ursprünglich fällig: ${format(parseISO(task.original_due_at), "dd.MM.yyyy HH:mm")}`}>
                {dueLabel(task.original_due_at)}
              </span>
            )}
            {category && (
              <span
                className="rounded px-1.5 py-0.5 text-xs"
                style={category.color ? { backgroundColor: category.color + "33" } : undefined}
              >
                {category.name}
              </span>
            )}
            {task.waiting_for && <span>wartet auf: {task.waiting_for}</span>}
            {task.subtasks.length > 0 && (
              <span>
                {task.subtasks.filter((s) => s.is_done).length}/{task.subtasks.length} Subtasks
              </span>
            )}
            {task.tags.length > 0 && <span>🏷 {task.tags.join(", ")}</span>}
            {task.status !== "offen" && task.status !== "erledigt" && (
              <span>{STATUS_LABEL[task.status]}</span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 gap-1">
          <button onClick={() => setShowDetail((s) => !s)} className="btn text-xs">
            Details
          </button>
        </div>
      </div>

      {showDetail && (
        <div className="mt-3 border-t border-stone-200 pt-3 dark:border-stone-800">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Field
              label="Titel"
              value={task.title}
              editing={editing === "title"}
              onEdit={() => setEditing("title")}
              onSave={(v) => {
                patch({ title: v });
                setEditing(null);
              }}
              onCancel={() => setEditing(null)}
            />
            <DateTimeField
              label="Fällig"
              value={task.due_at}
              editing={editing === "due_at"}
              onEdit={() => setEditing("due_at")}
              onSave={async (iso) => {
                await patch({ due_at: iso });
                setEditing(null);
              }}
              onCancel={() => setEditing(null)}
            />
            {task.original_due_at && task.due_at !== task.original_due_at && (
              <div>
                <Label>Ursprünglich fällig</Label>
                <div className="px-2 py-1.5 text-sm text-stone-500 line-through">
                  {format(parseISO(task.original_due_at), "dd.MM.yyyy HH:mm", { locale: de })}
                </div>
              </div>
            )}
            {task.recurrence_rule && (
              <div>
                <Label>Wiederholung</Label>
                <div className="flex items-center gap-2 px-2 py-1.5 text-sm">
                  <span className="text-violet-600">{rruleLabel(task.recurrence_rule)}</span>
                  <span className="text-xs text-stone-400">
                    ({task.recurrence_rule})
                  </span>
                </div>
              </div>
            )}
            <div>
              <Label>Kategorie</Label>
              <select
                value={task.category_id ?? ""}
                onChange={(e) =>
                  patch({ category_id: e.target.value ? Number(e.target.value) : null })
                }
                className="input"
              >
                <option value="">— keine —</option>
                {categories?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label>Status</Label>
              <select
                value={task.status}
                onChange={(e) => patch({ status: e.target.value as Task["status"] })}
                className="input"
              >
                {Object.entries(STATUS_LABEL).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label>Priorität</Label>
              <select
                value={task.priority}
                onChange={(e) => patch({ priority: Number(e.target.value) as Task["priority"] })}
                className="input"
              >
                <option value="1">P1</option>
                <option value="2">P2</option>
                <option value="3">P3</option>
                <option value="4">P4</option>
              </select>
            </div>
            <div>
              <Label>Wartet auf</Label>
              <DeferredInput
                value={task.waiting_for ?? ""}
                placeholder="—"
                onSave={(v) => patch({ waiting_for: v || null })}
              />
            </div>
          </div>
          {task.description && (
            <div className="mt-2 text-sm text-stone-600 dark:text-stone-300">
              {task.description}
            </div>
          )}
          <div className="mt-3">
            <Label>Notizen</Label>
            <textarea
              className="input min-h-[3rem] resize-y"
              rows={2}
              defaultValue={task.notes ?? ""}
              placeholder="Kommentare, Gedanken, Fortschritt…"
              onBlur={(e) => patch({ notes: e.target.value || null })}
              onInput={(e) => {
                const el = e.currentTarget;
                el.style.height = "auto";
                el.style.height = el.scrollHeight + "px";
              }}
              onFocus={(e) => {
                const el = e.currentTarget;
                el.style.height = "auto";
                el.style.height = el.scrollHeight + "px";
              }}
            />
          </div>
          {task.subtasks.length > 0 && (
            <div className="mt-3">
              <Label>Subtasks</Label>
              <SubtaskList task={task} />
            </div>
          )}
          {task.source_text && (
            <details className="mt-2 text-xs text-stone-500">
              <summary className="cursor-pointer">Rohtext</summary>
              <p className="mt-1 whitespace-pre-wrap rounded bg-stone-50 p-2 dark:bg-stone-800">
                {task.source_text}
              </p>
            </details>
          )}
          <div className="mt-3 flex gap-2 border-t border-stone-200 pt-3 dark:border-stone-800">
            {task.source_text && (
              <button
                onClick={() => reparse.mutate(task.uuid)}
                className="btn text-xs"
                title="Mit LLM neu verarbeiten"
              >
                ↻ Neu verarbeiten
              </button>
            )}
            <button
              onClick={() => {
                if (confirm("Task wirklich löschen?")) del.mutate(task.uuid);
              }}
              className="btn text-xs text-red-600"
            >
              ✕ Löschen
            </button>
          </div>
        </div>
      )}
    </li>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <label className="mb-1 block text-xs text-stone-500">{children}</label>;
}

function DeferredInput({
  value,
  placeholder,
  onSave,
}: {
  value: string;
  placeholder?: string;
  onSave: (v: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => { setDraft(value); }, [value]);
  return (
    <input
      className="input"
      value={draft}
      placeholder={placeholder}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => { if (draft !== value) onSave(draft); }}
      onKeyDown={(e) => { if (e.key === "Enter") { (e.target as HTMLInputElement).blur(); } }}
    />
  );
}

function rruleLabel(rule: string): string {
  try {
    if (rule.startsWith("FREQ=WEEKLY;BYDAY=")) {
      const day = rule.split("BYDAY=")[1]?.split(";")[0];
      const days: Record<string, string> = {
        MO: "Montag", TU: "Dienstag", WE: "Mittwoch",
        TH: "Donnerstag", FR: "Freitag", SA: "Samstag", SU: "Sonntag",
      };
      if (day && days[day]) return `Jeden ${days[day]}`;
    }
    if (rule.startsWith("FREQ=WEEKLY")) return "Wöchentlich";
    if (rule.startsWith("FREQ=DAILY")) return "Täglich";
    if (rule.startsWith("FREQ=MONTHLY")) return "Monatlich";
    if (rule.startsWith("FREQ=YEARLY")) return "Jährlich";
    return "Wiederholend";
  } catch {
    return "Wiederholend";
  }
}

function Field({
  label,
  value,
  placeholder,
  editing,
  onEdit,
  onSave,
  onCancel,
}: {
  label: string;
  value: string;
  placeholder?: string;
  editing: boolean;
  onEdit: () => void;
  onSave: (v: string) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState(value);
  if (editing) {
    return (
      <div>
        <Label>{label}</Label>
        <div className="flex gap-1">
          <input
            className="input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSave(draft);
              if (e.key === "Escape") onCancel();
            }}
            autoFocus
          />
          <button onClick={() => onSave(draft)} className="btn-primary text-xs">
            ✓
          </button>
          <button onClick={onCancel} className="btn text-xs">
            ✕
          </button>
        </div>
      </div>
    );
  }
  return (
    <div>
      <Label>{label}</Label>
      <button
        onClick={onEdit}
        className="block w-full rounded border border-transparent px-2 py-1.5 text-left text-sm hover:border-stone-300 dark:hover:border-stone-700"
      >
        {value || <span className="text-stone-400">{placeholder || "—"}</span>}
      </button>
    </div>
  );
}

function DateTimeField({
  label,
  value,
  editing,
  onEdit,
  onSave,
  onCancel,
}: {
  label: string;
  value: string | null;
  editing: boolean;
  onEdit: () => void;
  onSave: (iso: string | null) => void;
  onCancel: () => void;
}) {
  const isoToLocal = (iso: string | null): string => {
    if (!iso) return "";
    const t = iso.replace("Z", "");
    return t.length >= 16 ? t.slice(0, 16) : t.slice(0, 10) + "T00:00";
  };

  const localToIso = (local: string): string => {
    if (!local) return "";
    const [datePart, timePart] = local.split("T");
    const time = timePart
      ? timePart.length >= 5 ? timePart.slice(0, 5) : timePart
      : "00:00";
    return `${datePart}T${time}:00`;
  };

  const inputRef = useRef<HTMLInputElement>(null);

  // Uncontrolled input: den defaultValue setzen wir beim Öffnen des Editors,
  // lesen den aktuellen Wert beim Schließen direkt aus dem DOM.
  // Kein useState/onChange — eliminiert jede Race-Condition mit dem
  // nativen Date-Picker-Popup.
  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.value = isoToLocal(value);
      inputRef.current.focus();
    }
  }, [editing, value]);

  function commit() {
    const raw = inputRef.current?.value ?? "";
    if (raw) {
      onSave(localToIso(raw));
    } else {
      onSave(null);
    }
  }

  if (editing) {
    return (
      <div>
        <Label>{label}</Label>
        <div className="flex gap-1">
          <input
            ref={inputRef}
            type="datetime-local"
            className="input flex-1"
            defaultValue={isoToLocal(value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") onCancel();
            }}
            autoFocus
          />
          <button onClick={commit} className="btn-primary text-xs" title="Speichern">
            ✓
          </button>
          <button onClick={onCancel} className="btn text-xs" title="Abbrechen">
            ✕
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Label>{label}</Label>
      <button
        onClick={onEdit}
        className="flex w-full items-center gap-2 rounded border border-transparent px-2 py-1.5 text-left text-sm hover:border-stone-300 dark:hover:border-stone-700"
      >
        <span className="text-stone-400">📅</span>
        <span>{value ? format(parseISO(value), "dd.MM.yyyy HH:mm", { locale: de }) : <span className="text-stone-400">kein Datum</span>}</span>
        {value && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onSave(null);
            }}
            className="ml-auto text-xs text-stone-400 hover:text-red-600"
            title="Datum entfernen"
          >
            ✕
          </button>
        )}
      </button>
    </div>
  );
}

function SubtaskList({ task }: { task: Task }) {
  return (
    <ul className="space-y-1">
      {task.subtasks.map((st) => (
        <li key={st.id} className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={st.is_done} readOnly className="h-3.5 w-3.5" />
          <span className={clsx("flex-1", st.is_done && "text-stone-400 line-through")}>
            {st.title}
          </span>
        </li>
      ))}
    </ul>
  );
}
