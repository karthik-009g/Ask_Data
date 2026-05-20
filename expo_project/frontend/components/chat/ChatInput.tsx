"use client";

import type { KeyboardEvent } from "react";

type ChatInputProps = {
  value: string;
  loading: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
};

export default function ChatInput({ value, loading, onChange, onSubmit }: ChatInputProps) {
  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <div className="sticky bottom-0 border-t border-sky-200/80 bg-white/85 p-3 backdrop-blur-md">
      <div className="mx-auto flex max-w-4xl items-center gap-2">
        <input
          value={value}
          disabled={loading}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about employees, connections, or system"
          className="h-11 flex-1 rounded-xl border border-sky-200 bg-white/90 px-4 text-sm text-slate-900 outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-200"
        />
        <button
          type="button"
          disabled={loading || !value.trim()}
          onClick={onSubmit}
          className="h-11 rounded-xl bg-gradient-to-r from-sky-500 via-cyan-500 to-emerald-500 px-5 text-sm font-semibold text-white shadow-[0_10px_20px_rgba(14,165,233,0.26)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Sending..." : "Send"}
        </button>
      </div>
    </div>
  );
}
