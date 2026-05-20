const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api/proxy";
const DIRECT_BASES = (process.env.NEXT_PUBLIC_DIRECT_API_BASES || "")
  .split(",")
  .map((item) => item.trim())
  .filter(Boolean);
const FALLBACK_BASES = ["/api/proxy", ...DIRECT_BASES];

class ApiRequestError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function formatErrorMessage(text: string, status: number) {
  if (!text) {
    return `Request failed (${status})`;
  }

  try {
    const parsed = JSON.parse(text);
    if (typeof parsed?.detail === "string" && parsed.detail.trim()) {
      const detail = parsed.detail.trim();
      if (detail.toLowerCase().includes("unable to reach backend service")) {
        const reason = typeof parsed?.reason === "string" && parsed.reason.trim() ? ` (${parsed.reason.trim()})` : "";
        return `Cannot contact backend API${reason}. Please ensure backend is running at http://127.0.0.1:8000 and try again.`;
      }
      return detail;
    }
  } catch {
  }

  const lowered = text.toLowerCase();
  if (
    lowered.includes("proxy connection failed")
    || lowered.includes("fetch failed")
    || lowered.includes("failed to fetch")
    || lowered.includes("networkerror")
  ) {
    return "Cannot contact backend API. Please ensure backend is running at http://127.0.0.1:8000 and try again.";
  }

  return text;
}

async function tryRequest(base: string, path: string, options: RequestInit, headers: HeadersInit) {
  const response = await fetch(`${base}${path}`, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new ApiRequestError(response.status, formatErrorMessage(text, response.status));
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.blob();
}

export async function apiRequest(path: string, token?: string, options: RequestInit = {}) {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  const orderedBases = [API_BASE, ...FALLBACK_BASES.filter((item) => item !== API_BASE)];
  let lastError: unknown = null;

  for (const base of orderedBases) {
    try {
      return await tryRequest(base, path, options, headers);
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message.toLowerCase() : "";
      const shouldRetryByMessage = message.includes("failed to fetch") || message.includes("networkerror") || message.includes("load failed") || message.includes("not found");
      const shouldRetryByStatus = error instanceof ApiRequestError && (error.status >= 500 || error.status === 404);
      const shouldRetry = shouldRetryByMessage || shouldRetryByStatus;
      if (!shouldRetry) {
        throw error;
      }
    }
  }

  if (lastError instanceof Error) {
    const lowered = lastError.message.toLowerCase();
    if (
      lowered.includes("failed to fetch")
      || lowered.includes("fetch failed")
      || lowered.includes("networkerror")
      || lowered.includes("load failed")
    ) {
      throw new Error("Cannot reach frontend proxy or backend API. Ensure frontend (localhost:3000) and backend (127.0.0.1:8000) are running, then retry.");
    }
    throw lastError;
  }
  throw new Error("Request failed");
}
