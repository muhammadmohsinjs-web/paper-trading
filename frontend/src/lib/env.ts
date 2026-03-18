const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api";

export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? DEFAULT_API_BASE_URL;

export const wsBaseUrl =
  process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "") ??
  apiBaseUrl.replace(/^http/, "ws").replace(/\/api$/, "");
