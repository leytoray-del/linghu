import axios, { AxiosError } from "axios";

/** Error shape returned by the backend: { code, message, details: { fields? } }. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: Record<string, string>;
  /** A short heading the server suggests for this error, when it has one. */
  readonly title: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    fields: Record<string, string> = {},
    title: string | null = null,
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.title = title;
  }
}

const CSRF_COOKIE = "erf_csrf";
const UNSAFE = new Set(["post", "put", "patch", "delete"]);

function readCookie(name: string): string | null {
  const match = document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler = () => {};

/** The router registers how to react when the session has ended. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  onUnauthorized = handler;
}

export const http = axios.create({
  baseURL: "/api/v1",
  withCredentials: true,
  timeout: 30000,
});

http.interceptors.request.use((config) => {
  if (config.method && UNSAFE.has(config.method.toLowerCase())) {
    const token = readCookie(CSRF_COOKIE);
    if (token) config.headers.set("X-CSRF-Token", token);
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (
    error: AxiosError<{
      code?: string;
      message?: string;
      details?: { fields?: Record<string, string>; title?: string };
    }>,
  ) => {
    if (!error.response) {
      return Promise.reject(
        new ApiError(
          0,
          "network",
          "The server could not be reached. Check your connection and try again.",
        ),
      );
    }
    const { status, data } = error.response;
    const isLogin = error.config?.url?.includes("/auth/login");
    if (status === 401 && !isLogin) onUnauthorized();
    return Promise.reject(
      new ApiError(
        status,
        data?.code ?? "error",
        data?.message ?? "Something went wrong. Try again in a moment.",
        data?.details?.fields ?? {},
        typeof data?.details?.title === "string" ? data.details.title : null,
      ),
    );
  },
);
