const DEFAULT_BACKEND_BASE_URL = "http://35.228.198.216:8000";
const DEFAULT_API_BASE_URL = `${DEFAULT_BACKEND_BASE_URL}/api`;

export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? DEFAULT_API_BASE_URL;

export const backendBaseUrl =
  process.env.NEXT_PUBLIC_BACKEND_BASE_URL?.replace(/\/$/, "") ??
  apiBaseUrl.replace(/\/api$/, "");

export const wsBaseUrl =
  process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "") ??
  apiBaseUrl.replace(/^http/, "ws");
