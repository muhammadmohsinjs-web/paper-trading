const DEFAULT_LOCAL_BACKEND_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_PROD_BACKEND_BASE_URL = "http://35.228.198.216:8000";

function normalizeUrl(value: string | undefined) {
  return value?.trim().replace(/\/$/, "");
}

function resolveApiTarget(value: string | undefined) {
  const normalized = value?.trim().toLowerCase();
  if (normalized === "local") {
    return "local";
  }
  if (normalized === "prod") {
    return "prod";
  }
  return process.env.NODE_ENV === "development" ? "local" : "prod";
}

const apiTarget = resolveApiTarget(process.env.NEXT_PUBLIC_API_TARGET);
const configuredApiBaseUrl = normalizeUrl(process.env.NEXT_PUBLIC_API_BASE_URL);
const configuredBackendBaseUrl = normalizeUrl(process.env.NEXT_PUBLIC_BACKEND_BASE_URL);
const targetBackendBaseUrl =
  apiTarget === "local"
    ? normalizeUrl(process.env.NEXT_PUBLIC_LOCAL_BACKEND_BASE_URL) ?? DEFAULT_LOCAL_BACKEND_BASE_URL
    : normalizeUrl(process.env.NEXT_PUBLIC_PROD_BACKEND_BASE_URL) ?? DEFAULT_PROD_BACKEND_BASE_URL;
const externalBackendBaseUrl = configuredBackendBaseUrl ?? targetBackendBaseUrl;
const externalApiBaseUrl =
  configuredApiBaseUrl && /^https?:\/\//.test(configuredApiBaseUrl)
    ? configuredApiBaseUrl
    : `${externalBackendBaseUrl}/api`;
const browserApiBaseUrl =
  configuredApiBaseUrl && !/^https?:\/\//.test(configuredApiBaseUrl) ? configuredApiBaseUrl : "/api";

export const resolvedApiTarget = apiTarget;

export const apiBaseUrl =
  typeof window === "undefined" ? externalApiBaseUrl : browserApiBaseUrl;

export const backendBaseUrl = externalBackendBaseUrl;

export const wsBaseUrl =
  normalizeUrl(process.env.NEXT_PUBLIC_WS_URL) ?? externalApiBaseUrl.replace(/^http/, "ws");
