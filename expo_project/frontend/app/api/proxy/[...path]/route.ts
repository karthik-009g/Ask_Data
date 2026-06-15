import { NextRequest, NextResponse } from "next/server";

const primaryBackendBase = process.env.BACKEND_INTERNAL_URL?.trim();
const configuredBackendBases = (process.env.BACKEND_INTERNAL_URLS || "")
  .split(",")
  .map((item) => item.trim())
  .filter(Boolean);

// Keep local dev deterministic: prefer the canonical backend on :8000 first,
// then try configured alternatives.
const backendBases = Array.from(
  new Set([
    "http://127.0.0.1:8000/api/v1",
    ...(primaryBackendBase ? [primaryBackendBase] : []),
    ...configuredBackendBases,
    "http://127.0.0.1:8010/api/v1",
  ])
);

const upstreamResponseBodyHeaders = [
  "content-encoding",
  "content-length",
  "transfer-encoding",
];

async function proxy(request: NextRequest, context: { params: { path: string[] } }) {
  const path = (context.params.path || []).join("/");
  const query = request.nextUrl.search || "";

  const outgoingHeaders = new Headers(request.headers);
  [
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "upgrade",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
  ].forEach((header) => outgoingHeaders.delete(header));
  const requestBody = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();

  let lastError: unknown = null;

  for (const base of backendBases) {
    const targetUrl = `${base}/${path}${query}`;
    try {
      const response = await fetch(targetUrl, {
        method: request.method,
        headers: outgoingHeaders,
        body: requestBody,
        redirect: "manual",
      });

      const isAnalyticsPath = path === "employee/analyse" || path === "admin/analyse";
      if (response.status >= 500 || (isAnalyticsPath && response.status >= 400)) {
        const errorBody = await response.clone().text();
        console.error("[proxy] upstream error", {
          method: request.method,
          targetUrl,
          status: response.status,
          body: errorBody.slice(0, 1000),
        });
      }

      const responseHeaders = new Headers(response.headers);
      upstreamResponseBodyHeaders.forEach((header) => responseHeaders.delete(header));
      responseHeaders.set("x-proxy-target", targetUrl);
      return new NextResponse(response.body, {
        status: response.status,
        headers: responseHeaders,
      });
    } catch (error) {
      lastError = error;
      continue;
    }
  }

  const message = lastError instanceof Error ? lastError.message : "Proxy request failed";
  return NextResponse.json(
    {
      detail:
        "Unable to reach backend service. The API server may be stopped, starting up, or unreachable from the frontend proxy.",
      reason: message,
      backend_targets: backendBases,
      hint: "Start backend on http://127.0.0.1:8000 and retry.",
    },
    { status: 502 }
  );
}

export async function GET(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context);
}

export async function PUT(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context);
}

export async function PATCH(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context);
}

export async function DELETE(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context);
}

export async function OPTIONS(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context);
}
