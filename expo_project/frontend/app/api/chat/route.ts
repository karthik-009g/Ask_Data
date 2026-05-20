import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();
    const query = String(payload?.query || "").trim();
    if (!query) {
      return NextResponse.json({ type: "error", message: "Query is required", data: {}, next_steps: [] }, { status: 400 });
    }

    const auth = request.headers.get("authorization") || "";
    const backendResponse = await fetch(`${request.nextUrl.origin}/api/proxy/system-assistant/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(auth ? { Authorization: auth } : {}),
      },
      body: JSON.stringify({ user_query: query }),
      cache: "no-store",
    });

    const body = await backendResponse.text();
    return new NextResponse(body, {
      status: backendResponse.status,
      headers: { "Content-Type": backendResponse.headers.get("content-type") || "application/json" },
    });
  } catch {
    return NextResponse.json(
      { type: "error", message: "Failed to process chat request", data: {}, next_steps: [] },
      { status: 500 }
    );
  }
}
