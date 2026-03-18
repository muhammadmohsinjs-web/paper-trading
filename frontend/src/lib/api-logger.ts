import pc from "picocolors";

type ApiLogEntry = {
  method: string;
  url: string;
  status?: number;
  statusText?: string;
  durationMs: number;
  error?: unknown;
};

function colorMethod(method: string) {
  switch (method.toUpperCase()) {
    case "GET":
      return pc.cyan(method);
    case "POST":
      return pc.green(method);
    case "PUT":
      return pc.yellow(method);
    case "PATCH":
      return pc.magenta(method);
    case "DELETE":
      return pc.red(method);
    default:
      return pc.white(method);
  }
}

function colorStatus(status: number) {
  if (status >= 500) {
    return pc.red(String(status));
  }
  if (status >= 400) {
    return pc.yellow(String(status));
  }
  if (status >= 300) {
    return pc.blue(String(status));
  }
  return pc.green(String(status));
}

function formatUrl(url: string) {
  try {
    const parsed = new URL(url);
    return `${parsed.pathname}${parsed.search}`;
  } catch {
    return url;
  }
}

export function logApiRequest(entry: ApiLogEntry) {
  if (typeof window !== "undefined" || process.env.NODE_ENV === "test") {
    return;
  }

  const timestamp = new Date().toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
  const method = colorMethod(entry.method.toUpperCase().padEnd(6));
  const url = pc.bold(formatUrl(entry.url));
  const duration = pc.magenta(`${entry.durationMs}ms`);

  if (entry.error) {
    const message = entry.error instanceof Error ? entry.error.message : String(entry.error);
    console.error(`${pc.dim(timestamp)} ${pc.dim("[next-api]")} ${method} ${url} ${pc.red("FETCH_ERR")} ${duration} ${pc.red(message)}`);
    return;
  }

  const status = colorStatus(entry.status ?? 0);
  const statusText = entry.statusText ? pc.dim(entry.statusText) : "";
  console.log(`${pc.dim(timestamp)} ${pc.dim("[next-api]")} ${method} ${url} ${status} ${statusText} ${duration}`.trimEnd());
}
