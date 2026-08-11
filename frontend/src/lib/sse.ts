import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

export function useSSE() {
  const qc = useQueryClient();
  useEffect(() => {
    const access = localStorage.getItem("kapture.access");
    if (!access) return;
    const es = new EventSource("/api/v1/events", { withCredentials: false });
    es.addEventListener("llm.done", () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
    });
    es.addEventListener("task.updated", () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
    });
    es.addEventListener("llm.failed", () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
    });
    return () => es.close();
  }, [qc]);
}
