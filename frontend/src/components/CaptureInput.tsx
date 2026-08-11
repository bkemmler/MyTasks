import { useState, useRef, useEffect, type FormEvent } from "react";
import { useCapture } from "../lib/queries";

interface Props {
  autoFocus?: boolean;
  placeholder?: string;
  onDone?: () => void;
  viewTitle?: string;
  taskCount?: number;
}

type Mode = "enter" | "shift-enter";

const MODE_KEY = "kapture.capture-mode";

function getInitialMode(): Mode {
  if (typeof localStorage === "undefined") return "enter";
  const stored = localStorage.getItem(MODE_KEY);
  return stored === "shift-enter" ? "shift-enter" : "enter";
}

export function CaptureInput({ autoFocus, placeholder, onDone, viewTitle, taskCount }: Props) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<Mode>(getInitialMode);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const capture = useCapture();

  useEffect(() => {
    localStorage.setItem(MODE_KEY, mode);
  }, [mode]);

  function submit() {
    const value = text.trim();
    if (!value || capture.isPending) return;
    capture.mutate(value, {
      onSuccess: () => {
        setText("");
        onDone?.();
        inputRef.current?.focus();
      },
    });
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter") {
      const wantsNewline =
        mode === "enter" ? e.shiftKey : !e.shiftKey;
      if (wantsNewline) {
        return;
      }
      e.preventDefault();
      submit();
    } else if (e.key === "Escape") {
      if (text) {
        setText("");
      } else {
        onDone?.();
      }
    }
  }

  const hint =
    mode === "enter"
      ? "Enter erfasst · Shift+Enter neue Zeile"
      : "Shift+Enter erfasst · Enter neue Zeile";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <textarea
        ref={inputRef}
        autoFocus={autoFocus}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder ?? "Was ist zu tun? (Enter erfasst · #Kategorie · Zeilen für mehrere Tasks)"}
        rows={3}
        className="input resize-none"
      />
      <div className="mt-2 flex items-center gap-2 text-xs text-stone-500">
        {viewTitle != null && (
          <span className="whitespace-nowrap font-medium text-stone-700 dark:text-stone-300">
            {viewTitle} ({taskCount ?? 0})
          </span>
        )}
        <span className="flex-1 text-center">{hint}</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setMode(mode === "enter" ? "shift-enter" : "enter")}
            className="rounded border border-stone-300 px-2 py-0.5 hover:bg-stone-100 dark:border-stone-600 dark:hover:bg-stone-800"
            title="Erfassungs-Tastatur-Verhalten umschalten"
          >
            {mode === "enter" ? "⏎ Enter erfasst" : "⏎ Shift+Enter erfasst"}
          </button>
          <span>
            {text.length} / 5000
          </span>
        </div>
      </div>
      {capture.error && (
        <p className="mt-2 text-sm text-red-600">
          Fehler: {(capture.error as Error).message}
        </p>
      )}
    </form>
  );
}
