"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { apiRequest } from "../../lib/api";
import ResultChart from "../../components/ResultChart";
import SchemaERDiagram from "../../components/SchemaERDiagram";
import VisualWorkflow from "../../components/VisualWorkflow";

const PENDING_CHAT_QUERY_KEY = "systemAssistant.pendingQuery";

function parseJwt(token: string): Record<string, any> {
  try {
    const payload = token.split(".")[1];
    return JSON.parse(atob(payload));
  } catch {
    return {};
  }
}

function isLikelyAnalyticsPrompt(prompt: string): boolean {
  const text = String(prompt || "").trim().toLowerCase();
  if (!text) return false;

  const words = text.replace(/[^a-z0-9_\s]/g, " ").split(/\s+/).filter(Boolean);
  const greetingOnly = new Set(["hi", "hello", "hey", "yo", "ok", "thanks", "thank", "help"]);
  if (words.length <= 2 && words.every((word) => greetingOnly.has(word))) {
    return false;
  }

  const blockedPhrases = [
    "tell me a joke",
    "write a poem",
    "what is the weather",
    "who are you",
    "how are you",
    "good morning",
    "good night",
    "what can you do",
    "tasks you can perform",
    "list of tasks you can perform",
    "your capabilities",
  ];
  if (blockedPhrases.some((phrase) => text.includes(phrase))) {
    return false;
  }

  if (/\b(tasks?|capabilit(?:y|ies)|features?|functions?)\b.*\b(you can|can you|perform|do)\b/.test(text)) {
    return false;
  }

  const guidancePromptPatterns = [
    /\byou can read\b.*\btables?\b.*\b(help me|suggest|generate|example|sample)\b.*\bqueries?\b/,
    /\b(help me|can you)\b.*\b(generate|suggest|write|create)\b.*\b(simple\s+)?queries?\b.*\b(natural language|nlq)\b/,
    /\b(what can i ask|example prompts?|sample prompts?)\b.*\b(tables?|data|schema)\b/,
  ];
  if (guidancePromptPatterns.some((pattern) => pattern.test(text))) {
    return false;
  }

  const blockedWords = new Set([
    "joke",
    "poem",
    "story",
    "weather",
    "temperature",
    "news",
    "movie",
    "music",
    "song",
    "translate",
    "translation",
    "task",
    "tasks",
    "capability",
    "capabilities",
  ]);
  if (words.some((word) => blockedWords.has(word))) {
    return false;
  }

  const analyticsSignals = new Set([
    "id",
    "ids",
    "count",
    "sum",
    "avg",
    "average",
    "min",
    "max",
    "total",
    "top",
    "bottom",
    "highest",
    "lowest",
    "trend",
    "compare",
    "distribution",
    "group",
    "filter",
    "where",
    "between",
    "monthly",
    "weekly",
    "daily",
    "yearly",
    "revenue",
    "sales",
    "profit",
    "order",
    "orders",
    "customer",
    "customers",
    "employee",
    "employees",
    "attendance",
    "score",
    "marks",
    "table",
    "tables",
    "column",
    "columns",
    "records",
    "rows",
    "data",
    "report",
    "summary",
    "insight",
    "details",
    "calculate",
    "compute",
    "sql",
    "query",
    "queries",
  ]);
  if (words.some((word) => analyticsSignals.has(word))) {
    return true;
  }

  const phraseSignals = [
    "how many",
    "number of",
    "total number of",
    "show me",
    "list all",
    "top ",
    "bottom ",
    "last month",
    "this month",
    "last week",
    "this week",
  ];
  if (phraseSignals.some((phrase) => text.includes(phrase))) {
    return true;
  }

  const comparativeSignals = new Set([
    "less",
    "least",
    "more",
    "most",
    "highest",
    "lowest",
    "under",
    "over",
    "below",
    "above",
    "having",
    "with",
  ]);
  const timeSignals = new Set([
    "month",
    "months",
    "week",
    "weeks",
    "year",
    "years",
    "quarter",
    "quarters",
    "daily",
    "weekly",
    "monthly",
    "yearly",
    "today",
    "yesterday",
  ]);
  const entitySignals = new Set(["sales", "revenue", "profit", "order", "orders", "customer", "customers", "employee", "employees", "attendance"]);
  const actionSignals = new Set(["show", "list", "find", "fetch", "get", "give", "calculate", "compute", "analyze", "analyse", "compare"]);

  const hasComparative = words.some((word) => comparativeSignals.has(word));
  const hasTime = words.some((word) => timeSignals.has(word));
  const hasEntity = words.some((word) => entitySignals.has(word));
  const hasAction = words.some((word) => actionSignals.has(word));

  if (hasComparative && hasEntity) {
    return true;
  }

  if (hasEntity && (hasAction || hasTime || hasComparative)) {
    return true;
  }

  return false;
}

export default function EmployeePage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<"profile" | "view-connection" | "schema" | "data-analyse">("profile");
  const [token, setToken] = useState("");
  const [organisationName, setOrganisationName] = useState("");
  const [profile, setProfile] = useState<any>(null);
  const [profileForm, setProfileForm] = useState({
    full_name: "",
    position: "",
    department: "",
    phone: "",
    manager_name: "",
    location: "",
    timezone: "",
    preferred_language: "",
    bio: "",
  });
  const [profileNotice, setProfileNotice] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [connections, setConnections] = useState<any[]>([]);
  const [selectedDataSourceId, setSelectedDataSourceId] = useState<number | null>(null);
  const [schema, setSchema] = useState<any[]>([]);
  const [schemaConnectionId, setSchemaConnectionId] = useState<number | null>(null);

  const [analysisPrompt, setAnalysisPrompt] = useState("");
  const [analysisConnectionIds, setAnalysisConnectionIds] = useState<number[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  const [generatedQueries, setGeneratedQueries] = useState<any[]>([]);
  const [generationInfo, setGenerationInfo] = useState<any>(null);
  const [agenticTrace, setAgenticTrace] = useState<any>(null);
  const [overview, setOverview] = useState("");
  const [zeroRowReason, setZeroRowReason] = useState("");
  const [analytics, setAnalytics] = useState<any>(null);
  const [duration, setDuration] = useState(0);
  const [chartType, setChartType] = useState<"bar" | "line" | "pie" | "scatter" | "area">("bar");
  const [labelFeature, setLabelFeature] = useState("");
  const [valueFeature, setValueFeature] = useState("");
  const [studioPanel, setStudioPanel] = useState<"generated" | "agentic" | "workflow" | "overview" | "analytics" | "trends" | "downloads" | "plots" | "results">("generated");
  const [error, setError] = useState("");
  const [analysisRedirectNotice, setAnalysisRedirectNotice] = useState("");
  const [isAnalysisRunning, setIsAnalysisRunning] = useState(false);
  const [showAnalysisBuffer, setShowAnalysisBuffer] = useState(false);
  const [analysisSelectionSnapshot, setAnalysisSelectionSnapshot] = useState<number[]>([]);
  const [governanceUsage, setGovernanceUsage] = useState<any>(null);

  const columns = useMemo(() => (rows.length ? Object.keys(rows[0]) : []), [rows]);
  function hasPermission(connection: any, key: "can_read" | "can_query" | "can_visualize" | "can_export") {
    if (!connection?.permissions) return true;
    const value = connection.permissions[key];
    if (typeof value === "boolean") return value;
    return true;
  }

  const connectionById = useMemo(() => {
    const map: Record<number, any> = {};
    for (const connection of connections) {
      map[Number(connection.id)] = connection;
    }
    return map;
  }, [connections]);

  const canExportSelected = useMemo(() => {
    if (!analysisConnectionIds.length) return false;
    return analysisConnectionIds.every((id) => hasPermission(connectionById[id], "can_export"));
  }, [analysisConnectionIds, connectionById]);

  const canVisualizeSelected = useMemo(() => {
    if (!analysisConnectionIds.length) return false;
    return analysisConnectionIds.every((id) => hasPermission(connectionById[id], "can_visualize"));
  }, [analysisConnectionIds, connectionById]);
  const accessSummary = useMemo(() => {
    const withRead = connections.filter((item) => hasPermission(item, "can_read")).length;
    const withQuery = connections.filter((item) => hasPermission(item, "can_query")).length;
    const withVisualize = connections.filter((item) => hasPermission(item, "can_visualize")).length;
    const withExport = connections.filter((item) => hasPermission(item, "can_export")).length;
    return { withRead, withQuery, withVisualize, withExport };
  }, [connections]);
  const selectedDataSource = useMemo(
    () => connections.find((connection) => Number(connection.id) === Number(selectedDataSourceId)) || null,
    [connections, selectedDataSourceId]
  );

  useEffect(() => {
    const t = localStorage.getItem("token") || "";
    setToken(t);
    const payload = parseJwt(t);
    const org = String(payload.organisation || payload.org || "").trim();
    setOrganisationName(org);
    if (!t) {
      router.push("/");
      return;
    }
    void Promise.all([loadConnections(t), loadProfile(t), loadGovernanceUsage(t)]).catch((err: unknown) => {
      const message = err instanceof Error ? err.message : "Failed to load employee dashboard";
      setError(message);
    });
  }, []);

  async function loadGovernanceUsage(t: string) {
    const usage = await apiRequest("/employee/governance-usage", t);
    setGovernanceUsage(usage);
  }

  async function loadProfile(t: string) {
    const data = await apiRequest("/employee/profile", t);
    setProfile(data);
    setProfileForm({
      full_name: data?.full_name || "",
      position: data?.position || "",
      department: data?.department || "",
      phone: data?.phone || "",
      manager_name: data?.manager_name || "",
      location: data?.location || "",
      timezone: data?.timezone || "",
      preferred_language: data?.preferred_language || "",
      bio: data?.bio || "",
    });
  }

  async function saveProfile() {
    setError("");
    setProfileNotice("");
    setSavingProfile(true);
    try {
      const response = await apiRequest("/employee/profile", token, {
        method: "PATCH",
        body: JSON.stringify(profileForm),
      });
      setProfileNotice("Profile saved successfully.");
      if (response?.profile) {
        const data = response.profile;
        setProfile(data);
        setProfileForm({
          full_name: data?.full_name || "",
          position: data?.position || "",
          department: data?.department || "",
          phone: data?.phone || "",
          manager_name: data?.manager_name || "",
          location: data?.location || "",
          timezone: data?.timezone || "",
          preferred_language: data?.preferred_language || "",
          bio: data?.bio || "",
        });
      } else {
        await loadProfile(token);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to save profile";
      setError(message);
    } finally {
      setSavingProfile(false);
    }
  }

  async function loadConnections(t: string) {
    const list = await apiRequest("/employee/connections", t);
    setConnections(list);
    const queryEnabledIds = list
      .filter((connection: any) => hasPermission(connection, "can_query"))
      .map((connection: any) => Number(connection.id));
    setAnalysisConnectionIds(queryEnabledIds);

    if (list.length) {
      const firstId = Number(list[0].id);
      setSelectedDataSourceId(firstId);
      setSchemaConnectionId(firstId);
      await loadSchema(t, firstId);
    } else {
      setSelectedDataSourceId(null);
    }
  }

  async function loadSchema(t: string, connectionId: number) {
    const s = await apiRequest(`/employee/schema?connection_id=${connectionId}`, t);
    setSchema(s);
  }

  function toggleConnection(connectionId: number) {
    setAnalysisConnectionIds((prev) =>
      prev.includes(connectionId) ? prev.filter((id) => id !== connectionId) : [...prev, connectionId]
    );
  }

  async function runAnalysis() {
    if (isAnalysisRunning) {
      return;
    }
    setError("");
    setAnalysisRedirectNotice("");
    setRows([]);
    setGeneratedQueries([]);
    setGenerationInfo(null);
    setAgenticTrace(null);
    setOverview("");
    setAnalytics(null);
    setDuration(0);
    setZeroRowReason("");
    const promptText = analysisPrompt;
    const trimmedPrompt = promptText.trim();
    if (!trimmedPrompt) {
      setError("Enter a prompt");
      return;
    }
    const selectedConnectionSnapshot = [...analysisConnectionIds];
    setAnalysisSelectionSnapshot(selectedConnectionSnapshot);

    let spinnerDelayTimer: ReturnType<typeof window.setTimeout> | null = null;
    setIsAnalysisRunning(true);
    spinnerDelayTimer = window.setTimeout(() => {
      setShowAnalysisBuffer(true);
    }, 220);

    try {
      const data = await apiRequest("/employee/analyse", token, {
        method: "POST",
        body: JSON.stringify({ prompt: promptText, connection_ids: selectedConnectionSnapshot, mode: "analytics" }),
      });

      if (data?.agentic?.intent?.name === "non-analytics") {
        setAnalysisRedirectNotice("Detected non-analytics request, sending to System Assistant...");
        try {
          localStorage.setItem(
            PENDING_CHAT_QUERY_KEY,
            JSON.stringify({
              query: trimmedPrompt,
              source: "employee.analytics-studio",
              createdAt: Date.now(),
            })
          );
        } catch {
        }
        window.setTimeout(() => {
          router.push("/chat");
        }, 900);
        return;
      }

      setRows(data.rows || []);
      setGeneratedQueries(data.generated_queries || []);
      setGenerationInfo(data.generation || null);
      setAgenticTrace(data.agentic || null);
      setOverview(data.overview || "");
      setAnalytics(data.analytics || null);
      setDuration(data.execution_time || 0);
      const firstZeroRowReason = data.zero_row_reason || data.zero_row_diagnostics?.[0]?.reason || "";
      setZeroRowReason(firstZeroRowReason);

      const nextColumns = data.rows?.length ? Object.keys(data.rows[0]) : [];
      setLabelFeature(nextColumns[0] || "");
      setValueFeature(nextColumns[1] || nextColumns[0] || "");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Analysis failed";
      setError(message);
      setAnalysisRedirectNotice("");
      setAgenticTrace(null);
      setRows([]);
      setGeneratedQueries([]);
      setGenerationInfo(null);
      setOverview("");
      setAnalytics(null);
      setDuration(0);
      setZeroRowReason("");
    } finally {
      if (spinnerDelayTimer) {
        window.clearTimeout(spinnerDelayTimer);
      }
      setShowAnalysisBuffer(false);
      setIsAnalysisRunning(false);
    }
  }

  async function exportAnalysis(formatType: "csv" | "excel" | "pdf") {
    setError("");
    if (!analysisPrompt.trim() || !analysisConnectionIds.length) {
      setError("Select at least one connection and enter a prompt before download");
      return;
    }
    if (!canExportSelected) {
      setError("Export access is not enabled for one or more selected connections");
      return;
    }
    try {
      const blob = await apiRequest(`/employee/analyse/export/${formatType}`, token, {
        method: "POST",
        body: JSON.stringify({ prompt: analysisPrompt, connection_ids: analysisConnectionIds }),
        headers: { "Content-Type": "application/json" },
      });
      const url = URL.createObjectURL(blob as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `analysis.${formatType === "excel" ? "xlsx" : formatType}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Export failed";
      setError(message);
    }
  }

  async function logout() {
    try {
      if (token) {
        await apiRequest("/auth/logout", token, { method: "POST" });
      }
    } catch {
    } finally {
      localStorage.removeItem("token");
      router.push("/");
    }
  }

  return (
    <main className="role-theme role-employee page-stagger min-h-screen bg-gradient-to-br from-slate-100 via-indigo-50 to-blue-100 p-4 md:p-8">
      <div className="w-full max-w-[96rem] mx-auto space-y-6">
      <header className="space-y-3 bg-white/90 border border-slate-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-2">
            <Image src="/expo_logo-removebg-preview.png" alt="Ask Data" width={240} height={240} priority className="h-auto w-[200px] sm:w-[220px]" />
            <h1 className="text-3xl font-bold tracking-tight text-slate-900">Analyst Workspace</h1>
            <p className="text-sm font-medium text-slate-600">Query assigned sources and produce analytics-ready outputs.</p>
            <div className="flex flex-wrap items-center gap-2 text-xs md:text-sm">
              <span className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 font-semibold text-sky-800">
                Employee: {profile?.full_name || "-"}
              </span>
              <span className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 font-semibold text-indigo-800">
                Organisation: {profile?.organisation || organisationName || "-"}
              </span>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <button
              onClick={() => router.push("/chat")}
              className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 py-2 text-sm font-semibold"
            >
              System Assistant
            </button>
            <button onClick={logout} className="bg-slate-800 hover:bg-slate-900 text-white rounded-lg px-4 py-2 text-sm font-semibold">Logout</button>
          </div>
        </div>
      </header>

      <div className="space-y-4">
        <section className="bg-white/90 border border-slate-200 p-4 rounded-2xl shadow-sm">
          <p className="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-3">Modules</p>
          <div className="module-bar">
            <button onClick={() => setActiveTab("profile")} className={`module-tab text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "profile" ? "is-active" : ""}`}>Profile</button>
            <button onClick={() => setActiveTab("view-connection")} className={`module-tab text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "view-connection" ? "is-active" : ""}`}>Data Sources</button>
            <button onClick={() => setActiveTab("schema")} className={`module-tab text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "schema" ? "is-active" : ""}`}>Schema Browser</button>
            <button onClick={() => setActiveTab("data-analyse")} className={`module-tab text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "data-analyse" ? "is-active" : ""}`}>Analytics Studio</button>
          </div>
        </section>

        <section className="bg-white/90 border border-slate-200 p-4 rounded-2xl shadow-sm space-y-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs uppercase tracking-wide text-slate-500 font-semibold">Daily Governance Limits</p>
            <button onClick={() => loadGovernanceUsage(token)} className="rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700">Refresh</button>
          </div>
          <div className="stagger-grid grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
            <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2">
              <p className="text-slate-600">Queries (Today)</p>
              <p className="font-semibold text-slate-900">{governanceUsage?.usage?.queries_today ?? 0} / {governanceUsage?.limits?.max_queries_per_employee_per_day ?? "-"}</p>
              <p className="text-xs text-slate-600">Remaining: {governanceUsage?.usage?.queries_remaining ?? "-"}</p>
            </div>
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
              <p className="text-slate-600">Exports (Today)</p>
              <p className="font-semibold text-slate-900">{governanceUsage?.usage?.exports_today ?? 0} / {governanceUsage?.limits?.max_exports_per_employee_per_day ?? "-"}</p>
              <p className="text-xs text-slate-600">Remaining: {governanceUsage?.usage?.exports_remaining ?? "-"}</p>
            </div>
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2">
              <p className="text-slate-600">Max Rows Per Query</p>
              <p className="font-semibold text-slate-900">{governanceUsage?.limits?.max_rows_per_query ?? "-"}</p>
              <p className="text-xs text-slate-600">Per query execution cap</p>
            </div>
          </div>
        </section>

      {activeTab === "profile" && (
        <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4">
          <h2 className="font-semibold">Profile</h2>
          <div className="stagger-grid grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <label className="space-y-1"><span className="text-slate-600 text-xs font-medium">Full Name</span><input className="w-full border rounded p-2" value={profileForm.full_name} onChange={(e) => setProfileForm((prev) => ({ ...prev, full_name: e.target.value }))} /></label>
            <label className="space-y-1"><span className="text-slate-600 text-xs font-medium">Position</span><input className="w-full border rounded p-2" value={profileForm.position} onChange={(e) => setProfileForm((prev) => ({ ...prev, position: e.target.value }))} /></label>
            <label className="space-y-1"><span className="text-slate-600 text-xs font-medium">Department</span><input className="w-full border rounded p-2" value={profileForm.department} onChange={(e) => setProfileForm((prev) => ({ ...prev, department: e.target.value }))} /></label>
            <label className="space-y-1"><span className="text-slate-600 text-xs font-medium">Phone</span><input className="w-full border rounded p-2" value={profileForm.phone} onChange={(e) => setProfileForm((prev) => ({ ...prev, phone: e.target.value }))} /></label>
            <label className="space-y-1"><span className="text-slate-600 text-xs font-medium">Manager Name</span><input className="w-full border rounded p-2" value={profileForm.manager_name} onChange={(e) => setProfileForm((prev) => ({ ...prev, manager_name: e.target.value }))} /></label>
            <label className="space-y-1"><span className="text-slate-600 text-xs font-medium">Location</span><input className="w-full border rounded p-2" value={profileForm.location} onChange={(e) => setProfileForm((prev) => ({ ...prev, location: e.target.value }))} /></label>
            <label className="space-y-1"><span className="text-slate-600 text-xs font-medium">Timezone</span><input className="w-full border rounded p-2" value={profileForm.timezone} onChange={(e) => setProfileForm((prev) => ({ ...prev, timezone: e.target.value }))} /></label>
            <label className="space-y-1"><span className="text-slate-600 text-xs font-medium">Preferred Language</span><input className="w-full border rounded p-2" value={profileForm.preferred_language} onChange={(e) => setProfileForm((prev) => ({ ...prev, preferred_language: e.target.value }))} /></label>
            <label className="space-y-1 md:col-span-2"><span className="text-slate-600 text-xs font-medium">Bio</span><textarea className="w-full border rounded p-2 h-24" value={profileForm.bio} onChange={(e) => setProfileForm((prev) => ({ ...prev, bio: e.target.value }))} /></label>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={saveProfile} disabled={savingProfile} className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-60">{savingProfile ? "Saving..." : "Save Profile"}</button>
            {profileNotice && <p className="text-sm text-emerald-700">{profileNotice}</p>}
          </div>

          <h3 className="text-sm font-semibold text-slate-700">Connection Access Summary</h3>
          <div className="overflow-auto rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b bg-slate-50">
                  <th className="p-2">Connection</th>
                  <th className="p-2">Type</th>
                  <th className="p-2">Read</th>
                  <th className="p-2">Query</th>
                  <th className="p-2">Visualize</th>
                  <th className="p-2">Export</th>
                </tr>
              </thead>
              <tbody>
                {connections.map((connection) => (
                  <tr key={connection.id} className="border-b">
                    <td className="p-2">#{connection.id} {connection.name}</td>
                    <td className="p-2">{connection.db_type}</td>
                    <td className="p-2">{hasPermission(connection, "can_read") ? "Yes" : "No"}</td>
                    <td className="p-2">{hasPermission(connection, "can_query") ? "Yes" : "No"}</td>
                    <td className="p-2">{hasPermission(connection, "can_visualize") ? "Yes" : "No"}</td>
                    <td className="p-2">{hasPermission(connection, "can_export") ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {activeTab === "view-connection" && (
        <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm">
          <h2 className="font-semibold mb-2">Data Sources</h2>
          {connections.length === 0 ? (
            <p className="text-sm text-slate-600">No connections assigned yet.</p>
          ) : (
            <div className="space-y-3">
              <div className="overflow-auto rounded-lg border border-slate-200">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left border-b">
                      <th className="p-2">Connection</th>
                      <th className="p-2">Type</th>
                      <th className="p-2">Read</th>
                      <th className="p-2">Query</th>
                      <th className="p-2">Visualize</th>
                      <th className="p-2">Export</th>
                    </tr>
                  </thead>
                  <tbody>
                    {connections.map((connection) => (
                      <tr
                        key={connection.id}
                        className={`border-b cursor-pointer ${Number(connection.id) === Number(selectedDataSourceId) ? "bg-blue-50" : "hover:bg-slate-50"}`}
                        onClick={() => setSelectedDataSourceId(Number(connection.id))}
                      >
                        <td className="p-2">#{connection.id} {connection.name}</td>
                        <td className="p-2">{connection.db_type}</td>
                        <td className="p-2">{hasPermission(connection, "can_read") ? "Yes" : "No"}</td>
                        <td className="p-2">{hasPermission(connection, "can_query") ? "Yes" : "No"}</td>
                        <td className="p-2">{hasPermission(connection, "can_visualize") ? "Yes" : "No"}</td>
                        <td className="p-2">{hasPermission(connection, "can_export") ? "Yes" : "No"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {selectedDataSource && (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <h3 className="text-sm font-semibold text-slate-800">Assigned Tables for #{selectedDataSource.id} {selectedDataSource.name}</h3>
                  {Array.isArray(selectedDataSource?.permissions?.allowed_tables) && selectedDataSource.permissions.allowed_tables.includes("*") ? (
                    <p className="mt-2 text-sm text-slate-700">All tables are assigned for this database.</p>
                  ) : (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {(selectedDataSource?.permissions?.allowed_tables || []).map((tableName: string) => (
                        <span key={`${selectedDataSource.id}-${tableName}`} className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-800">
                          {tableName}
                        </span>
                      ))}
                      {(!selectedDataSource?.permissions?.allowed_tables || selectedDataSource.permissions.allowed_tables.length === 0) && (
                        <p className="text-sm text-slate-700">No table access assigned yet.</p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {activeTab === "schema" && (
        <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm overflow-auto space-y-3">
          <h2 className="font-semibold">Schema Browser</h2>
          <select
            className="border rounded p-2"
            value={schemaConnectionId ?? ""}
            onChange={async (e) => {
              const id = Number(e.target.value);
              setSchemaConnectionId(id);
              await loadSchema(token, id);
            }}
          >
            <option value="" disabled>Select Connection</option>
            {connections.map((connection) => (
              <option key={connection.id} value={connection.id}>#{connection.id} {connection.name}</option>
            ))}
          </select>

          {schemaConnectionId ? (
            <div className="space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-slate-700 mb-2">Entity Relationship Diagram</h3>
                <SchemaERDiagram rows={schema} />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-700 mb-2">Schema Table View</h3>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left border-b"><th>Table</th><th>Column</th><th>Type</th><th>Relation</th></tr>
                  </thead>
                  <tbody>
                    {schema.map((item) => (
                      <tr key={item.id} className="border-b">
                        <td>{item.table_name}</td>
                        <td>{item.column_name}</td>
                        <td>{item.data_type}</td>
                        <td>{item.relationship_info || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-600">Select a connection to view schema.</p>
          )}
        </section>
      )}

      {activeTab === "data-analyse" && (
        <>
          <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4">
            <div className="rounded-2xl border border-blue-200 bg-blue-50/60 p-4 space-y-3">
              <div>
                <p className="text-xs uppercase tracking-wide text-blue-700 font-semibold">Analytics Query Chat</p>
                <h3 className="text-lg font-bold text-slate-900">Ask in natural language, execute as SQL</h3>
                <p className="text-sm text-slate-600 mt-1">This chatbox is for analytics execution. Your question is converted to SQL (with guardrails), executed, and shown in results.</p>
              </div>
              <textarea
                className="w-full border border-slate-300 rounded-xl p-3 h-24 bg-white"
                value={analysisPrompt}
                onChange={(e) => setAnalysisPrompt(e.target.value)}
                placeholder="Example: show top 10 customers by revenue in last 30 days"
              />
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => runAnalysis()}
                  disabled={isAnalysisRunning}
                  aria-busy={isAnalysisRunning}
                  className="query-run-btn bg-blue-600 hover:bg-blue-700 text-white rounded-xl px-5 py-2.5 font-semibold disabled:opacity-80 disabled:cursor-not-allowed"
                >
                  <span className="inline-flex items-center gap-2">
                    {showAnalysisBuffer && <span className="query-run-spinner" aria-hidden="true" />}
                    <span>{isAnalysisRunning ? "Running Analytics..." : "Run Analytics Query"}</span>
                  </span>
                </button>
              </div>
              {analysisRedirectNotice && (
                <p className="rounded-xl border border-sky-300 bg-sky-50/90 px-3 py-2 text-sky-800 text-sm font-medium">
                  {analysisRedirectNotice}
                </p>
              )}
              {error && <p className="text-red-600 text-sm font-medium">{error}</p>}
              {!error && generatedQueries.length === 0 && agenticTrace?.intent?.name === "non-analytics" && (
                <p className="rounded-xl border border-amber-300 bg-amber-50/90 px-3 py-2 text-amber-800 text-sm font-medium">
                  Non-analytics prompt: no SQL generated.
                </p>
              )}
              {!error && rows.length === 0 && generatedQueries.length > 0 && zeroRowReason && (
                <p className="text-amber-700 text-sm font-medium">No rows reason: {zeroRowReason}</p>
              )}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><p className="text-slate-500">Selected</p><p className="font-semibold">{analysisConnectionIds.length}</p></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><p className="text-slate-500">Rows</p><p className="font-semibold">{rows.length}</p></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><p className="text-slate-500">Time</p><p className="font-semibold">{duration ? `${duration.toFixed(3)}s` : "-"}</p></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><p className="text-slate-500">Generated</p><p className="font-semibold">{generatedQueries.length}</p></div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {connections.map((connection) => (
                <label key={connection.id} className={`flex items-center justify-between gap-2 border rounded-xl p-3 text-sm transition-colors ${analysisConnectionIds.includes(connection.id) ? "border-blue-300 bg-blue-50" : "border-slate-200 bg-slate-50 hover:bg-slate-100"}`}>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={analysisConnectionIds.includes(connection.id)}
                      onChange={() => toggleConnection(connection.id)}
                      disabled={!hasPermission(connection, "can_query")}
                    />
                    <span className="font-medium">#{connection.id} {connection.name}</span>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-semibold text-slate-500 uppercase">{connection.db_type}</span>
                    {!hasPermission(connection, "can_query") && (
                      <p className="text-[11px] font-medium text-amber-700">No query permission</p>
                    )}
                  </div>
                </label>
              ))}
            </div>
            {connections.length === 0 && <p className="text-sm text-slate-600">No assigned connections available for analysis.</p>}

          </section>

          <section className="grid grid-cols-1 lg:grid-cols-[230px_minmax(0,1fr)] gap-4">
            <aside className="bg-white/90 border border-slate-200 rounded-2xl p-4 shadow-sm h-fit lg:sticky lg:top-4 space-y-2">
              <p className="text-xs uppercase tracking-wide text-slate-500 font-semibold">Studio Features</p>
              <button onClick={() => setStudioPanel("generated")} className={`w-full text-left rounded-lg px-3 py-2 text-sm font-semibold ${studioPanel === "generated" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Generated Queries</button>
              <button onClick={() => setStudioPanel("agentic")} className={`w-full text-left rounded-lg px-3 py-2 text-sm font-semibold ${studioPanel === "agentic" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Agentic Flow</button>
              <button onClick={() => setStudioPanel("workflow")} className={`w-full text-left rounded-lg px-3 py-2 text-sm font-semibold ${studioPanel === "workflow" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Visual Workflow</button>
              <button onClick={() => setStudioPanel("overview")} className={`w-full text-left rounded-lg px-3 py-2 text-sm font-semibold ${studioPanel === "overview" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Overview</button>
              <button onClick={() => setStudioPanel("analytics")} className={`w-full text-left rounded-lg px-3 py-2 text-sm font-semibold ${studioPanel === "analytics" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Analytical Values</button>
              <button onClick={() => setStudioPanel("trends")} className={`w-full text-left rounded-lg px-3 py-2 text-sm font-semibold ${studioPanel === "trends" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Trend Watch</button>
              <button onClick={() => setStudioPanel("downloads")} className={`w-full text-left rounded-lg px-3 py-2 text-sm font-semibold ${studioPanel === "downloads" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Downloads</button>
              <button onClick={() => setStudioPanel("plots")} className={`w-full text-left rounded-lg px-3 py-2 text-sm font-semibold ${studioPanel === "plots" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Plots</button>
              <button onClick={() => setStudioPanel("results")} className={`w-full text-left rounded-lg px-3 py-2 text-sm font-semibold ${studioPanel === "results" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Results</button>
            </aside>

            <div className="bg-white/90 border border-slate-200 rounded-2xl p-5 shadow-sm overflow-auto space-y-3">
              {studioPanel === "generated" && (
                <>
                  <h2 className="font-semibold">Generated Queries</h2>
                  {generationInfo && <p className="text-xs text-slate-600">Generation mode: {generationInfo.mode} ({generationInfo.provider} / {generationInfo.model})</p>}
                  <div className="overflow-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left border-b"><th>Connection</th><th>DB</th><th>Language</th><th>Query</th></tr>
                      </thead>
                      <tbody>
                        {generatedQueries.map((query, index) => (
                          <tr key={index} className="border-b">
                            <td>{query.connection_name}</td>
                            <td>{query.db_type}</td>
                            <td>{query.query_language}</td>
                            <td className="whitespace-pre-wrap text-xs leading-5">{query.query_text}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-sm text-slate-700">Execution Time: {duration.toFixed(4)}s</p>
                </>
              )}

              {studioPanel === "agentic" && (
                <>
                  <h2 className="font-semibold">Agentic Flow</h2>
                  <p className="text-sm text-slate-600">Planner, policy, repair, and insight steps run as bounded agents before the result is shown.</p>
                  {!agenticTrace && (
                    <div className="space-y-2">
                      <p className="text-sm text-slate-600">Run analysis to inspect the workflow.</p>
                      {error ? <p className="text-sm text-red-600">Current issue: {error}</p> : null}
                    </div>
                  )}
                  {agenticTrace && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                        <div className="rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2">
                          <p className="text-slate-600">Planner</p>
                          <p className="font-semibold text-slate-900">{agenticTrace?.summary?.selected_connections ?? 0} connection(s)</p>
                          <p className="text-xs text-slate-600">SQL: {agenticTrace?.summary?.sql_connections ?? 0} | Mongo: {agenticTrace?.summary?.mongodb_connections ?? 0}</p>
                        </div>
                        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2">
                          <p className="text-slate-600">Policy</p>
                          <p className="font-semibold text-slate-900">Read-only enforced</p>
                          <p className="text-xs text-slate-600">Row cap: {agenticTrace?.connections?.[0]?.policy?.max_rows ?? governanceUsage?.limits?.max_rows_per_query ?? "-"}</p>
                        </div>
                        <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2">
                          <p className="text-slate-600">Repair</p>
                          <p className="font-semibold text-slate-900">{agenticTrace?.connections?.[0]?.repair?.attempts?.length ?? 0} attempt(s)</p>
                          <p className="text-xs text-slate-600">Max: {agenticTrace?.connections?.[0]?.repair?.max_attempts ?? 0}</p>
                        </div>
                      </div>

                      <div className="space-y-3">
                        {Array.isArray(agenticTrace?.connections) && agenticTrace.connections.map((step: any, index: number) => (
                          <div key={`${step?.planner?.connection_id ?? index}`} className="rounded-2xl border border-slate-200 bg-slate-50 p-4 space-y-2">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div>
                                <p className="font-semibold text-slate-900">#{step?.planner?.connection_id ?? "-"} {step?.planner?.connection_name ?? "Connection"}</p>
                                <p className="text-xs text-slate-600 uppercase tracking-wide">{step?.planner?.db_type || "unknown"}</p>
                              </div>
                              <span className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-semibold text-slate-700">Confidence: {step?.planner?.confidence || "low"}</span>
                            </div>
                            <p className="text-sm text-slate-700">{step?.planner?.clarification_question || "The planner selected the best-fit source and moved to guarded execution."}</p>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-slate-600">
                              <div className="rounded-lg border border-slate-200 bg-white p-3">
                                <p className="font-semibold text-slate-800 mb-1">Top Tables</p>
                                <ul className="space-y-1">
                                  {(step?.planner?.matched_tables || []).map((table: any) => (
                                    <li key={table.table_name}>{table.table_name} {table.score !== undefined ? `(${table.score})` : ""}</li>
                                  ))}
                                </ul>
                              </div>
                              <div className="rounded-lg border border-slate-200 bg-white p-3">
                                <p className="font-semibold text-slate-800 mb-1">Insight Signals</p>
                                <ul className="space-y-1">
                                  {(step?.insight?.signals || []).map((signal: string, signalIndex: number) => (
                                    <li key={`${signalIndex}-${signal}`}>{signal}</li>
                                  ))}
                                </ul>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}

              {studioPanel === "workflow" && (
                <>
                  <h2 className="font-semibold">Visual Workflow</h2>
                  <p className="text-sm text-slate-600">See how prompt interpretation, model routing, source selection, SQL generation, guardrails, and results were sequenced.</p>
                  <VisualWorkflow
                    prompt={analysisPrompt}
                    selectedConnectionIds={analysisSelectionSnapshot}
                    generatedQueries={generatedQueries}
                    generationInfo={generationInfo}
                    agenticTrace={agenticTrace}
                    executionTime={duration}
                    rowCount={rows.length}
                    errorMessage={error}
                  />
                </>
              )}

              {studioPanel === "overview" && (
                <>
                  <h2 className="font-semibold">Overview</h2>
                  <p className="text-sm text-slate-700 whitespace-pre-wrap">{overview || "Run analysis to get overview."}</p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <p className="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Tables Used</p>
                      <p className="text-sm text-slate-700">{(agenticTrace?.tables_used || []).length ? (agenticTrace?.tables_used || []).join(", ") : "No explicit table extraction available."}</p>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                      <p className="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-1">Planner Scope</p>
                      <p className="text-sm text-slate-700">{(agenticTrace?.tables_in_scope || []).length ? (agenticTrace?.tables_in_scope || []).join(", ") : "Planner scope unavailable."}</p>
                    </div>
                  </div>
                  {!!(agenticTrace?.proactive_alerts || []).length && (
                    <div className="space-y-2">
                      <p className="text-xs uppercase tracking-wide text-rose-700 font-semibold">Proactive Alerts</p>
                      <ul className="space-y-1">
                        {(agenticTrace?.proactive_alerts || []).map((alert: string, index: number) => (
                          <li key={`${index}-${alert}`} className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900">{alert}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}

              {studioPanel === "analytics" && (
                <>
                  <h2 className="font-semibold">Analytical Values</h2>
                  <p className="text-sm">Total Rows: {analytics?.row_count ?? 0}</p>
                  <p className="text-xs text-slate-600">Technical numeric fields hidden: {(analytics?.suppressed_numeric_columns || []).join(", ") || "none"}</p>
                  {!!(agenticTrace?.trend_snapshot?.weekly_changes || []).length && (
                    <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                      <p className="font-semibold">Last 1 Week Trend Snapshot</p>
                      <ul className="mt-1 space-y-1">
                        {(agenticTrace?.trend_snapshot?.weekly_changes || []).map((item: any) => (
                          <li key={item.metric}>{item.metric}: {item.pct_change === null ? "new vs previous week" : `${item.pct_change}%`} ({item.previous_week} to {item.this_week})</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <div className="overflow-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left border-b"><th>Feature</th><th>Count</th><th>Sum</th><th>Avg</th><th>Min</th><th>Max</th></tr>
                      </thead>
                      <tbody>
                        {Object.entries(analytics?.business_numeric_columns || analytics?.numeric_columns || {}).map(([feature, stats]: any) => (
                          <tr key={feature} className="border-b">
                            <td>{feature}</td>
                            <td>{stats.count}</td>
                            <td>{stats.sum}</td>
                            <td>{stats.avg}</td>
                            <td>{stats.min}</td>
                            <td>{stats.max}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}

              {studioPanel === "trends" && (
                <>
                  <h2 className="font-semibold">Trend Watch</h2>
                  <p className="text-sm text-slate-600">Automatically shows meaningful trends and proactive alerts when detected.</p>
                  {!!(agenticTrace?.proactive_alerts || []).length && (
                    <div className="space-y-2">
                      <p className="text-xs uppercase tracking-wide text-rose-700 font-semibold">Proactive Alerts</p>
                      <ul className="space-y-1">
                        {(agenticTrace?.proactive_alerts || []).map((alert: string, index: number) => (
                          <li key={`${index}-${alert}`} className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900">{alert}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {!!(agenticTrace?.trend_snapshot?.weekly_changes || []).length && (
                    <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                      <p className="font-semibold">Last 1 Week Trend Snapshot</p>
                      <ul className="mt-1 space-y-1">
                        {(agenticTrace?.trend_snapshot?.weekly_changes || []).map((item: any) => (
                          <li key={item.metric}>{item.metric}: {item.pct_change === null ? "new vs previous week" : `${item.pct_change}%`} ({item.previous_week} to {item.this_week})</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {!((agenticTrace?.proactive_alerts || []).length || (agenticTrace?.trend_snapshot?.weekly_changes || []).length) && (
                    <p className="text-sm text-slate-600">No strong trends detected for this result set yet. Run a time-based query for trend detection.</p>
                  )}
                </>
              )}

              {studioPanel === "downloads" && (
                <>
                  <h2 className="font-semibold">Downloads</h2>
                  {!rows.length && <p className="text-sm text-slate-600">Run analysis first to enable downloads.</p>}
                  {rows.length > 0 && !canExportSelected && <p className="text-sm text-amber-700">Export access is disabled for one or more selected sources.</p>}
                  {rows.length > 0 && canExportSelected && (
                    <div className="flex flex-wrap gap-2">
                      <button onClick={() => exportAnalysis("csv")} className="bg-slate-700 hover:bg-slate-800 text-white rounded-lg px-4 py-2">Download CSV</button>
                      <button onClick={() => exportAnalysis("excel")} className="bg-slate-700 hover:bg-slate-800 text-white rounded-lg px-4 py-2">Download Excel</button>
                      <button onClick={() => exportAnalysis("pdf")} className="bg-slate-700 hover:bg-slate-800 text-white rounded-lg px-4 py-2">Download PDF</button>
                    </div>
                  )}
                </>
              )}

              {studioPanel === "plots" && (
                <>
                  <h2 className="font-semibold">Plots</h2>
                  {!rows.length && <p className="text-sm text-slate-600">Run analysis first to visualize data.</p>}
                  {rows.length > 0 && !canVisualizeSelected && <p className="text-sm text-amber-700">Visualization access is disabled for one or more selected sources.</p>}
                  {rows.length > 0 && canVisualizeSelected && (
                    <>
                      <div className="flex flex-wrap gap-2">
                        <select className="border rounded px-2 py-1" value={chartType} onChange={(e) => setChartType(e.target.value as any)}>
                          <option value="bar">Bar</option>
                          <option value="line">Line</option>
                          <option value="pie">Pie</option>
                          <option value="scatter">Scatter</option>
                          <option value="area">Area</option>
                        </select>
                        <select className="border rounded px-2 py-1" value={labelFeature} onChange={(e) => setLabelFeature(e.target.value)}>
                          {columns.map((column) => (
                            <option key={column} value={column}>{column}</option>
                          ))}
                        </select>
                        <select className="border rounded px-2 py-1" value={valueFeature} onChange={(e) => setValueFeature(e.target.value)}>
                          {columns.map((column) => (
                            <option key={column} value={column}>{column}</option>
                          ))}
                        </select>
                      </div>
                      <ResultChart rows={rows} chartType={chartType} labelKey={labelFeature} valueKey={valueFeature} />
                    </>
                  )}
                </>
              )}

              {studioPanel === "results" && (
                <>
                  <h2 className="font-semibold">Results</h2>
                  {!rows.length && <p className="text-sm text-slate-600">Run analysis to view result rows.</p>}
                  {rows.length > 0 && (
                    <table className="w-full text-sm">
                      <thead>
                        <tr>
                          {Object.keys(rows[0]).map((key) => (
                            <th key={key} className="text-left border-b p-1">{key}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row, rowIndex) => (
                          <tr key={rowIndex}>
                            {Object.values(row).map((value: any, valueIndex) => (
                              <td key={valueIndex} className="border-b p-1">{String(value)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </>
              )}
            </div>
          </section>
        </>
      )}
        </div>
      </div>
    </main>
  );
}
