const defaultBackendBaseUrl = "http://35.228.198.216:8000";
const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
const configuredBackendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_BASE_URL?.replace(/\/$/, "");
const backendBaseUrl = configuredBackendBaseUrl ?? defaultBackendBaseUrl;
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
