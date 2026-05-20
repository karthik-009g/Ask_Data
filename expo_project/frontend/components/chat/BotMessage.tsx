"use client";

import { useState } from "react";
import { ChatMessage } from "./types";

type BotMessageProps = {
  message: ChatMessage;
  onStepClick: (step: string) => void;
};

function bubbleClass(responseType?: ChatMessage["responseType"]) {
  if (responseType === "error") {
    return "border border-rose-300 bg-rose-50 text-rose-900";
  }
  if (responseType === "redirect") {
    return "border border-amber-300 bg-amber-50 text-amber-900";
  }
  if (responseType === "action") {
    return "border border-sky-300 bg-gradient-to-r from-sky-50 to-cyan-50 text-slate-900";
  }
  return "border border-sky-200 bg-white/90 text-slate-900";
}

export default function BotMessage({ message, onStepClick }: BotMessageProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(message.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  const text = message.responseType === "redirect" ? "Forwarding to Data Assistant..." : message.text;
  const tablesRaw = message.assistantData?.["tables"];
  const columnsRaw = message.assistantData?.["columns"];
  const connectionsRaw = message.assistantData?.["connections"];
  const tables = Array.isArray(tablesRaw)
    ? (tablesRaw as unknown[]).map((item) => String(item)).filter(Boolean)
    : [];
  const columns = Array.isArray(columnsRaw)
    ? (columnsRaw as Array<Record<string, unknown>>)
    : [];
  const connections = Array.isArray(connectionsRaw)
    ? (connectionsRaw as Array<Record<string, unknown>>)
        .map((item) => {
          const id = String(item.id ?? "").trim();
          const name = String(item.name ?? "").trim();
          const databaseName = String(item.database_name ?? "").trim();
          const dbType = String(item.db_type ?? "").trim();
          return { id, name, databaseName, dbType };
        })
        .filter((item) => item.id || item.name || item.databaseName)
    : [];
  const databaseScopeRaw = message.assistantData?.["database_scope"];
  const databaseScope =
    databaseScopeRaw && typeof databaseScopeRaw === "object" && !Array.isArray(databaseScopeRaw)
      ? (databaseScopeRaw as Record<string, unknown>)
      : null;
  const scopedDatabase = databaseScope ? String(databaseScope["database"] || "").trim() : "";
  const requestedDatabase = databaseScope ? String(databaseScope["requested_database"] || "").trim() : "";
  const scopedConnectionIds = databaseScope && Array.isArray(databaseScope["connection_ids"])
    ? (databaseScope["connection_ids"] as unknown[]).map((item) => String(item)).filter(Boolean)
    : [];

  return (
    <div className="flex justify-start">
      <div className={`max-w-[85%] rounded-2xl px-4 py-3 shadow-[0_12px_24px_rgba(14,116,144,0.15)] backdrop-blur ${bubbleClass(message.responseType)}`}>
        <p className="whitespace-pre-wrap text-sm leading-relaxed">{text}</p>

        {(scopedDatabase || requestedDatabase || scopedConnectionIds.length > 0) && (
          <div className="mt-2 inline-flex flex-wrap items-center gap-2 rounded-full border border-cyan-300 bg-cyan-50 px-2.5 py-1 text-[11px] text-cyan-900">
            <span className="font-semibold">Scope</span>
            {scopedDatabase && <span>DB: {scopedDatabase}</span>}
            {!scopedDatabase && requestedDatabase && <span>Requested: {requestedDatabase}</span>}
            {scopedConnectionIds.length > 0 && <span>Connections: {scopedConnectionIds.join(", ")}</span>}
          </div>
        )}

        {tables.length > 0 && (
          <div className="mt-3 rounded-lg border border-sky-200 bg-white/80 p-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-600">Tables</p>
            <ul className="grid grid-cols-1 gap-1 text-sm text-slate-900 sm:grid-cols-2">
              {tables.map((tableName) => (
                <li key={`${message.id}-table-${tableName}`} className="rounded-md border border-sky-100 bg-sky-50/60 px-2 py-1">
                  {tableName}
                </li>
              ))}
            </ul>
          </div>
        )}

        {connections.length > 0 && (
          <div className="mt-3 rounded-lg border border-sky-200 bg-white/80 p-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-600">Assigned Databases</p>
            <ul className="space-y-2 text-sm text-slate-900">
              {connections.map((connection) => (
                <li key={`${message.id}-conn-${connection.id || connection.name || connection.databaseName}`} className="rounded-md border border-sky-100 bg-sky-50/60 px-2 py-2">
                  <p className="font-medium text-slate-900">{connection.databaseName || connection.name || "Unnamed"}</p>
                  <p className="text-xs text-slate-600">
                    {connection.name ? `Connection: ${connection.name}` : "Connection: -"}
                    {connection.id ? ` | ID: ${connection.id}` : ""}
                    {connection.dbType ? ` | Type: ${connection.dbType}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}

        {columns.length > 0 && (
          <div className="mt-3 overflow-auto rounded-lg border border-sky-200">
            <table className="min-w-full text-left text-xs text-slate-900">
              <thead className="bg-sky-50 text-slate-600">
                <tr>
                  <th className="px-2 py-2 font-semibold">Column</th>
                  <th className="px-2 py-2 font-semibold">Type</th>
                </tr>
              </thead>
              <tbody>
                {columns.map((column, idx) => (
                  <tr key={`${message.id}-col-${idx}`} className="border-t border-sky-100">
                    <td className="px-2 py-2">{String(column.column_name || "")}</td>
                    <td className="px-2 py-2">{String(column.data_type || "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={handleCopy}
            className="rounded-lg border border-sky-200 bg-white/90 px-2.5 py-1 text-xs text-slate-800 transition hover:border-sky-400"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>

        {message.responseType === "action" && (message.nextSteps || []).length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {(message.nextSteps || []).map((step, idx) => (
              <button
                key={`${message.id}-step-${idx}`}
                type="button"
                onClick={() => onStepClick(step)}
                className="rounded-lg border border-sky-200 bg-white/90 px-3 py-1.5 text-xs text-slate-800 transition hover:border-sky-400 hover:bg-sky-50"
              >
                {step}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
