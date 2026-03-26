const DEFAULT_BACKEND_BASE_URL = "http://35.228.198.216:8000";
const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
const configuredBackendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_BASE_URL?.replace(/\/$/, "");
const externalBackendBaseUrl = configuredBackendBaseUrl ?? DEFAULT_BACKEND_BASE_URL;
const externalApiBaseUrl =
  configuredApiBaseUrl && /^https?:\/\//.test(configuredApiBaseUrl)
    ? configuredApiBaseUrl
    : `${externalBackendBaseUrl}/api`;
const browserApiBaseUrl =
  configuredApiBaseUrl && !/^https?:\/\//.test(configuredApiBaseUrl) ? configuredApiBaseUrl : "/api";

export const apiBaseUrl =
  typeof window === "undefined" ? externalApiBaseUrl : browserApiBaseUrl;

export const backendBaseUrl =
  process.env.NEXT_PUBLIC_BACKEND_BASE_URL?.replace(/\/$/, "") ?? externalBackendBaseUrl;

export const wsBaseUrl =
  process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "") ??
  externalApiBaseUrl.replace(/^http/, "ws");
