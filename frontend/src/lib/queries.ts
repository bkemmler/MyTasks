import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type Priority = 1 | 2 | 3 | 4;
export type Status = "offen" | "in_bearbeitung" | "wartend" | "erledigt" | "abgebrochen";

export interface Subtask {
  id: number;
  title: string;
  is_done: boolean;
  sort_order: number;
  completed_at: string | null;
}

export interface Task {
  id: number;
  uuid: string;
  title: string;
  description: string | null;
  notes: string | null;
  source_text: string | null;
  due_at: string | null;
  original_due_at: string | null;
  due_is_all_day: boolean;
  start_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  category_id: number | null;
  priority: Priority;
  status: Status;
  progress_percent: number;
  estimated_minutes: number | null;
  waiting_for: string | null;
  location: string | null;
  url: string | null;
  recurrence_rule: string | null;
  llm_state: "none" | "pending" | "done" | "failed";
  llm_confidence: number | null;
  needs_review: boolean;
  review_notes: string | null;
  subtasks: Subtask[];
  tags: string[];
}

export interface Category {
  id: number;
  name: string;
  color: string | null;
  aliases: string | null;
  is_default: boolean;
  sort_order: number;
}

export interface AdminUser {
  id: number;
  username: string;
  email: string | null;
  display_name: string | null;
  is_admin: boolean;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
  updated_at: string;
}

export interface Health {
  status: string;
  version: string;
  uptime_seconds: number;
  ollama: string;
}

export interface VersionInfo {
  app: string;
  api: string;
  db_schema: string;
  git_sha: string;
  built_at: string;
  min_android: string;
}

export const QK = {
  tasks: (view: string, filters: object) => ["tasks", view, filters] as const,
  task: (uuid: string) => ["task", uuid] as const,
  categories: () => ["categories"] as const,
  tags: () => ["tags"] as const,
  users: () => ["admin", "users"] as const,
  health: () => ["health"] as const,
};

export function useTasks(view: string, params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: QK.tasks(view, params),
    queryFn: () => {
      const q = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => {
        if (v !== null && v !== undefined && v !== "") q.set(k, String(v));
      });
      return api<Task[]>(`/tasks?${q.toString()}`);
    },
  });
}

export function useTask(uuid: string) {
  return useQuery({
    queryKey: QK.task(uuid),
    queryFn: () => api<Task>(`/tasks/${uuid}`),
    enabled: !!uuid,
  });
}

export function useCategories() {
  return useQuery({
    queryKey: QK.categories(),
    queryFn: () => api<Category[]>("/categories"),
  });
}

export function useTags() {
  return useQuery({
    queryKey: QK.tags(),
    queryFn: () => api<{ name: string; task_count: number }[]>("/tags"),
  });
}

export function useUsers() {
  return useQuery({
    queryKey: QK.users(),
    queryFn: () => api<AdminUser[]>("/admin/users"),
  });
}

export function useHealth() {
  return useQuery({
    queryKey: QK.health(),
    queryFn: () => api<Health>("/health"),
    refetchInterval: 10_000,
  });
}

export function useVersion() {
  return useQuery({
    queryKey: ["version"],
    queryFn: () => api<VersionInfo>("/version"),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useCapture() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) =>
      api<Task[]>("/tasks/capture", {
        method: "POST",
        body: JSON.stringify({ text, mode: "auto" }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

export function useUpdateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Partial<Task> }) =>
      api<Task>(`/tasks/${uuid}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: (task) => {
      qc.setQueryData(QK.task(task.uuid), task);
      qc.setQueriesData<Task[]>(
        { queryKey: ["tasks"] },
        (old) => old?.map((t) => (t.uuid === task.uuid ? task : t)) ?? old,
      );
    },
  });
}

export function useCompleteTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api<Task>(`/tasks/${uuid}/complete`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useDeleteTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api<void>(`/tasks/${uuid}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useConfirmReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api<Task>(`/tasks/${uuid}/confirm-review`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useReparse() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api<Task>(`/tasks/${uuid}/reparse`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useAddSubtask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, title }: { uuid: string; title: string }) =>
      api<Subtask>(`/tasks/${uuid}/subtasks`, {
        method: "POST",
        body: JSON.stringify({ title }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useToggleSubtask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, subtask_id }: { uuid: string; subtask_id: number }) =>
      api<Subtask>(`/tasks/${uuid}/subtasks/${subtask_id}/toggle`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useDeleteSubtask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, subtask_id }: { uuid: string; subtask_id: number }) =>
      api<void>(`/tasks/${uuid}/subtasks/${subtask_id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}

export function useCreateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; color?: string; aliases?: string[] }) =>
      api<Category>("/categories", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.categories() }),
  });
}

export function useUpdateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<Category> }) =>
      api<Category>(`/categories/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.categories() }),
  });
}

export function useDeleteCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/categories/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.categories() }),
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      username: string;
      password: string;
      email?: string;
      display_name?: string;
      is_admin?: boolean;
    }) => api<AdminUser>("/admin/users", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.users() }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<AdminUser> }) =>
      api<AdminUser>(`/admin/users/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.users() }),
  });
}

export function useDeleteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, hard }: { id: number; hard: boolean }) =>
      api<void>(`/admin/users/${id}?hard=${hard}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.users() }),
  });
}
