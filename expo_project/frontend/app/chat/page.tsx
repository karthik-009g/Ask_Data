"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import BotMessage from "../../components/chat/BotMessage";
import ChatInput from "../../components/chat/ChatInput";
import UserMessage from "../../components/chat/UserMessage";
import { AssistantResponse, ChatMessage } from "../../components/chat/types";

const PENDING_CHAT_QUERY_KEY = "systemAssistant.pendingQuery";

function makeId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function parseApiError(text: string, status: number): string {
  if (!text) return `Request failed (${status})`;
  try {
    const parsed = JSON.parse(text);
    if (typeof parsed?.message === "string" && parsed.message.trim()) return parsed.message.trim();
    if (typeof parsed?.detail === "string" && parsed.detail.trim()) return parsed.detail.trim();
  } catch {
  }
  return text;
}

export default function ChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: makeId(),
      role: "bot",
      text: "System Assistant is ready. I can help with employees, permissions, metadata, and navigation.",
      responseType: "info",
      nextSteps: ["Show tables", "Describe students", "Columns in orders"],
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [token, setToken] = useState("");
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const autoDispatchHandledRef = useRef(false);

  const typingIndicator = useMemo(
    () =>
      loading ? (
        <div className="flex justify-start">
          <div className="rounded-xl border border-sky-200 bg-white/85 px-4 py-2 text-xs text-slate-600 shadow-sm backdrop-blur">
            Assistant is typing...
          </div>
        </div>
      ) : null,
    [loading]
  );

  useEffect(() => {
    const saved = localStorage.getItem("token") || "";
    if (!saved) {
      router.push("/");
      return;
    }
    setToken(saved);
  }, []);

  useEffect(() => {
    if (!scrollerRef.current) return;
    scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [messages, loading]);

  useEffect(() => {
    if (!token || loading || autoDispatchHandledRef.current) return;

    let pendingQuery = "";
    try {
      const raw = localStorage.getItem(PENDING_CHAT_QUERY_KEY) || "";
      if (!raw) return;
      localStorage.removeItem(PENDING_CHAT_QUERY_KEY);
      try {
        const parsed = JSON.parse(raw);
        pendingQuery = String(parsed?.query || "").trim();
      } catch {
        pendingQuery = String(raw || "").trim();
      }
    } catch {
      pendingQuery = "";
    }

    if (!pendingQuery) return;
    autoDispatchHandledRef.current = true;
    void sendQuery(pendingQuery);
  }, [token, loading]);

  async function sendQuery(rawQuery: string) {
    const query = String(rawQuery || "").trim();
    if (!query || loading) return;

    const userMessage: ChatMessage = {
      id: makeId(),
      role: "user",
      text: query,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ query }),
      });
      if (!res.ok) {
        const errorBody = await res.text();
        throw new Error(parseApiError(errorBody, res.status));
      }
      const response = (await res.json()) as AssistantResponse;

      const botMessage: ChatMessage = {
        id: makeId(),
        role: "bot",
        text: response.message || "No response message",
        responseType: response.type,
        nextSteps: response.next_steps || [],
        assistantData: response.data || {},
      };
      setMessages((prev) => [...prev, botMessage]);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Chat request failed";
      setMessages((prev) => [
        ...prev,
        {
          id: makeId(),
          role: "bot",
          text: message,
          responseType: "error",
          nextSteps: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function sendMessage() {
    await sendQuery(input);
  }

  function onStepClick(step: string) {
    setInput(step);
  }

  return (
    <main className="h-screen text-slate-900">
      <div className="mx-auto flex h-full min-h-0 max-w-5xl flex-col px-4 py-4 sm:px-6">
        <header className="mb-3 rounded-2xl border border-sky-200 bg-white/80 px-4 py-3 shadow-sm backdrop-blur">
          <h1 className="text-lg font-semibold">System Assistant</h1>
          <p className="text-xs text-slate-600">Operations, permissions, metadata, help, and navigation.</p>
        </header>

        <div
          ref={scrollerRef}
          className="flex-1 space-y-3 overflow-y-auto rounded-2xl border border-sky-200 bg-white/80 p-4 shadow-sm backdrop-blur"
        >
          {messages.map((message) =>
            message.role === "user" ? (
              <UserMessage key={message.id} message={message} />
            ) : (
              <BotMessage key={message.id} message={message} onStepClick={onStepClick} />
            )
          )}
          {typingIndicator}
        </div>

        <ChatInput value={input} loading={loading} onChange={setInput} onSubmit={sendMessage} />
      </div>
    </main>
  );
}
