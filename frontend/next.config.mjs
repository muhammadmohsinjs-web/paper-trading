const DEFAULT_LOCAL_BACKEND_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_PROD_BACKEND_BASE_URL = "http://35.228.198.216:8000";

function normalizeUrl(value) {
  return value?.trim().replace(/\/$/, "");
}

function normalizeApiTarget(value) {
  const normalized = value?.trim().toLowerCase();

  if (!normalized) {
    return undefined;
  }

  if (normalized === "local" || normalized === "development" || normalized === "dev") {
    return "local";
  }

  if (normalized === "prod" || normalized === "production") {
    return "prod";
  }

  return undefined;
}

function resolveApiTarget(...values) {
  for (const value of values) {
    const resolved = normalizeApiTarget(value);
    if (resolved) {
      return resolved;
    }
  }

  return process.env.NODE_ENV === "development" ? "local" : "prod";
}

const configuredApiBaseUrl = normalizeUrl(process.env.NEXT_PUBLIC_API_BASE_URL);
const configuredBackendBaseUrl = normalizeUrl(process.env.NEXT_PUBLIC_BACKEND_BASE_URL);
const apiTarget = resolveApiTarget(
  process.env.NEXT_PUBLIC_ENV,
  process.env.NEXT_PUBLIC_APP_ENV,
  process.env.NEXT_PUBLIC_API_TARGET
);
const targetBackendBaseUrl =
  apiTarget === "local"
    ? normalizeUrl(process.env.NEXT_PUBLIC_LOCAL_BACKEND_BASE_URL) ?? DEFAULT_LOCAL_BACKEND_BASE_URL
    : normalizeUrl(process.env.NEXT_PUBLIC_PROD_BACKEND_BASE_URL) ?? DEFAULT_PROD_BACKEND_BASE_URL;
const backendBaseUrl = configuredBackendBaseUrl ?? targetBackendBaseUrl;
const apiProxyBaseUrl =
  configuredApiBaseUrl && /^https?:\/\//.test(configuredApiBaseUrl)
    ? configuredApiBaseUrl
    : `${backendBaseUrl}/api`;

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiProxyBaseUrl}/:path*`
      }
    ];
  }
};

export default nextConfig;
