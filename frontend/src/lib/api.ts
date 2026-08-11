const ACCESS_KEY = "kapture.access";
const REFRESH_KEY = "kapture.refresh";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

let refreshPromise: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  const refresh = getRefreshToken();
  if (!refresh) return false;

  refreshPromise = (async () => {
    try {
      const resp = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!resp.ok) return false;
      const data = await resp.json();
      setTokens(data.access_token, data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const doFetch = async (): Promise<Response> => {
    const access = getAccessToken();
    const headers = new Headers(options.headers);
    if (access) headers.set("Authorization", `Bearer ${access}`);
    if (options.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    return fetch(`/api/v1${path}`, { ...options, headers });
  };

  let resp = await doFetch();
  if (resp.status === 401 && getRefreshToken()) {
    const ok = await tryRefresh();
    if (ok) resp = await doFetch();
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || body.title || detail;
    } catch {
      // ignore
    }
    if (resp.status === 401) {
      clearTokens();
      window.location.href = "/login";
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}
