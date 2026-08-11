import { useState, type FormEvent } from "react";
import { useCategories, useCreateCategory, useDeleteCategory, useUpdateCategory } from "../lib/queries";

export function Categories() {
  const { data: categories, isLoading } = useCategories();
  const create = useCreateCategory();
  const update = useUpdateCategory();
  const del = useDeleteCategory();
  const [name, setName] = useState("");
  const [color, setColor] = useState("#3b82f6");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    create.mutate(
      { name: name.trim(), color },
      {
        onSuccess: () => setName(""),
      },
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Kategorien</h1>

      <form onSubmit={submit} className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Neue Kategorie…"
          className="input flex-1"
        />
        <input
          type="color"
          value={color}
          onChange={(e) => setColor(e.target.value)}
          className="h-10 w-12 cursor-pointer rounded border border-stone-300"
        />
        <button type="submit" className="btn-primary" disabled={!name.trim()}>
          +
        </button>
      </form>

      {isLoading ? (
        <p>Lade…</p>
      ) : (
        <ul className="space-y-1">
          {categories?.map((c) => (
            <li
              key={c.id}
              className="flex items-center gap-2 rounded border border-stone-200 bg-white px-3 py-2 dark:border-stone-800 dark:bg-stone-900"
            >
              <input
                type="color"
                value={c.color ?? "#3b82f6"}
                onChange={(e) => update.mutate({ id: c.id, body: { color: e.target.value } })}
                className="h-6 w-8 cursor-pointer rounded border-0"
              />
              <span className="flex-1">{c.name}</span>
              <button
                onClick={() => {
                  if (confirm(`Kategorie "${c.name}" löschen?`)) del.mutate(c.id);
                }}
                className="btn text-xs text-red-600"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
