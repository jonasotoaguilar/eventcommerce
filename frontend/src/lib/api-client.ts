/** Backend error contract: every API error body carries `detail`. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export interface ApiClientOptions {
  baseUrl?: string;
  getToken?: () => string | null;
  onUnauthorized?: () => void;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  jsonBody?: unknown;
}

/**
 * Normalize a backend `{detail}` body into a human-actionable string.
 * Handles FastAPI shapes: plain string, `{"detail": [...]}` validation
 * errors, and unexpected bodies (falls back to status text, never leaks
 * raw internals beyond the backend-provided detail).
 */
export function extractDetail(body: unknown, fallback: string): string {
  if (body !== null && typeof body === "object") {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.length > 0) return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) =>
          typeof item === "string"
            ? item
            : item !== null && typeof item === "object"
              ? (item as { msg?: unknown }).msg
              : null,
        )
        .filter((msg): msg is string => typeof msg === "string" && msg.length > 0);
      if (messages.length > 0) return messages.join(". ");
    }
  }
  if (typeof body === "string" && body.length > 0) return body;
  return fallback;
}

const DEFAULT_BASE_URL = "/api/v1";

export function createApiClient(options: ApiClientOptions = {}) {
  const baseUrl = options.baseUrl ?? DEFAULT_BASE_URL;
  const getToken = options.getToken ?? (() => null);

  async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
    const { jsonBody, headers, ...rest } = init;
    const token = getToken();
    const response = await fetch(`${baseUrl}${path}`, {
      ...rest,
      headers: {
        ...(jsonBody !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: jsonBody === undefined ? undefined : JSON.stringify(jsonBody),
    });

    if (response.status === 401) {
      options.onUnauthorized?.();
    }

    if (!response.ok) {
      let parsed: unknown = null;
      try {
        parsed = await response.json();
      } catch {
        parsed = null;
      }
      throw new ApiError(
        response.status,
        extractDetail(parsed, `Request failed with status ${response.status}`),
      );
    }

    if (response.status === 204) return undefined as T;
    const text = await response.text();
    if (text.length === 0) return undefined as T;
    return JSON.parse(text) as T;
  }

  return {
    get: <T>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: "GET" }),
    post: <T>(path: string, body?: unknown, init?: RequestInit) =>
      request<T>(path, { ...init, method: "POST", jsonBody: body }),
    put: <T>(path: string, body?: unknown, init?: RequestInit) =>
      request<T>(path, { ...init, method: "PUT", jsonBody: body }),
    patch: <T>(path: string, body?: unknown, init?: RequestInit) =>
      request<T>(path, { ...init, method: "PATCH", jsonBody: body }),
    del: <T>(path: string, init?: RequestInit) =>
      request<T>(path, { ...init, method: "DELETE" }),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
