"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { apiRequest } from "../../lib/api";
import ResultChart from "../../components/ResultChart";
import { validatePassword, isPasswordStrong } from "../../lib/passwordValidator";
import { PasswordStrengthMeter } from "../../components/PasswordStrengthMeter";
import SchemaERDiagram from "../../components/SchemaERDiagram";
import HoverGuide from "../../components/HoverGuide";
import VisualWorkflow from "../../components/VisualWorkflow";

const PENDING_CHAT_QUERY_KEY = "systemAssistant.pendingQuery";

type ConnectionPayload = {
  name: string;
  db_type: string;
  method: string;
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  database_name?: string;
  connection_url?: string;
};

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

export default function AdminPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<"employee-add" | "access-control" | "add-connection" | "schema" | "data-analyse" | "enterprise">("employee-add");
  const [token, setToken] = useState("");
  const [adminName, setAdminName] = useState("");
  const [organisationName, setOrganisationName] = useState("");
  const [employees, setEmployees] = useState<any[]>([]);
  const [employeeSearch, setEmployeeSearch] = useState("");
  const [employeeCardPage, setEmployeeCardPage] = useState(1);
  const [connections, setConnections] = useState<any[]>([]);
  const [metadata, setMetadata] = useState<any[]>([]);
  const [schemaConnectionId, setSchemaConnectionId] = useState<number | null>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [pageError, setPageError] = useState("");

  const [employeeForm, setEmployeeForm] = useState({ full_name: "", email: "", position: "", password: "" });
  const [showEmployeePassword, setShowEmployeePassword] = useState(false);
  const [showEmployeePasswordStrength, setShowEmployeePasswordStrength] = useState(false);
  const employeePasswordStrength = validatePassword(employeeForm.password);
  const [employeeId, setEmployeeId] = useState<string>("");
  const [employeeDetailTab, setEmployeeDetailTab] = useState<"profile" | "assign-permission">("profile");
  const [removingEmployeeId, setRemovingEmployeeId] = useState("");
  const [permissionDraft, setPermissionDraft] = useState<Record<number, { can_read: boolean; can_query: boolean; can_visualize: boolean; can_export: boolean; allowed_tables: string[]; all_tables: boolean }>>({});
  const [permissionAssignLoading, setPermissionAssignLoading] = useState(false);
  const [permissionAssignNotice, setPermissionAssignNotice] = useState("");
  const [permissionAssignNoticeType, setPermissionAssignNoticeType] = useState<"success" | "error" | "info">("info");

  const [form, setForm] = useState<ConnectionPayload>({ name: "", db_type: "mysql", method: "form" });
  const [editingConnectionId, setEditingConnectionId] = useState<number | null>(null);
  const [connectionMessage, setConnectionMessage] = useState("");

  const [analysisPrompt, setAnalysisPrompt] = useState("");
  const [analysisConnectionIds, setAnalysisConnectionIds] = useState<number[]>([]);
  const [analysisRows, setAnalysisRows] = useState<any[]>([]);
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
  const [analysisError, setAnalysisError] = useState("");
  const [analysisRedirectNotice, setAnalysisRedirectNotice] = useState("");
  const [isAnalysisRunning, setIsAnalysisRunning] = useState(false);
  const [showAnalysisBuffer, setShowAnalysisBuffer] = useState(false);
  const [analysisSelectionSnapshot, setAnalysisSelectionSnapshot] = useState<number[]>([]);
  const [adminAnalysisUsage, setAdminAnalysisUsage] = useState<any>(null);

  const [auditTimeline, setAuditTimeline] = useState<any[]>([]);
  const [governanceLimits, setGovernanceLimits] = useState<any>({
    max_queries_per_day: 100,
    max_exports_per_day: 20,
    max_rows_per_query: 10000,
    alert_on_limit_breach: true,
  });
  const [scheduledReports, setScheduledReports] = useState<any[]>([]);
  const [connectionHealth, setConnectionHealth] = useState<any[]>([]);
  const [governanceUsage, setGovernanceUsage] = useState<any>(null);
  const [enterpriseMessage, setEnterpriseMessage] = useState("");
  const [enterpriseTab, setEnterpriseTab] = useState<"governance" | "schedules" | "health" | "audit">("governance");
  const [reportForm, setReportForm] = useState({
    name: "",
    prompt: "",
    format: "csv",
    interval_minutes: 60,
    recipient_email: "",
  });
  const [scheduleConnectionIds, setScheduleConnectionIds] = useState<number[]>([]);

  const analysisColumns = useMemo(() => (analysisRows.length ? Object.keys(analysisRows[0]) : []), [analysisRows]);
  const canExportSelected = useMemo(() => analysisConnectionIds.length > 0, [analysisConnectionIds]);
  const canVisualizeSelected = useMemo(() => analysisConnectionIds.length > 0, [analysisConnectionIds]);
  const tableOptionsByConnection = useMemo(() => {
    const map: Record<number, string[]> = {};
    for (const row of metadata) {
      const connectionId = Number(row.connection_id);
      const tableName = String(row.table_name || "").trim();
      if (!connectionId || !tableName) continue;
      if (!map[connectionId]) {
        map[connectionId] = [];
      }
      if (!map[connectionId].includes(tableName)) {
        map[connectionId].push(tableName);
      }
    }
    for (const key of Object.keys(map)) {
      map[Number(key)] = [...map[Number(key)]].sort((a, b) => a.localeCompare(b));
    }
    return map;
  }, [metadata]);
  const filteredSchemaRows = useMemo(
    () => metadata.filter((item) => schemaConnectionId === null || Number(item.connection_id) === Number(schemaConnectionId)),
    [metadata, schemaConnectionId]
  );
  const filteredEmployees = useMemo(() => {
    const query = employeeSearch.trim().toLowerCase();
    if (!query) return employees;
    return employees.filter((employee) => {
      const name = String(employee.full_name || "").toLowerCase();
      const email = String(employee.email || "").toLowerCase();
      const position = String(employee.position || "").toLowerCase();
      return name.includes(query) || email.includes(query) || position.includes(query);
    });
  }, [employees, employeeSearch]);
  const employeeCardsPerPage = 6;
  const totalEmployeeCardPages = Math.max(1, Math.ceil(filteredEmployees.length / employeeCardsPerPage));
  const visibleEmployeeCards = useMemo(() => {
    const start = (employeeCardPage - 1) * employeeCardsPerPage;
    return filteredEmployees.slice(start, start + employeeCardsPerPage);
  }, [filteredEmployees, employeeCardPage]);
  const selectedEmployee = useMemo(
    () => employees.find((employee) => employee.id === employeeId) || null,
    [employees, employeeId]
  );
  const employeeById = useMemo(() => {
    const map: Record<string, any> = {};
    for (const employee of employees) {
      map[String(employee.id)] = employee;
    }
    return map;
  }, [employees]);

  useEffect(() => {
    const t = localStorage.getItem("token") || "";
    setToken(t);
    const payload = parseJwt(t);
    const org = String(payload.organisation || payload.org || "").trim();
    const displayName = String(payload.full_name || payload.name || payload.email || "").trim();
    setAdminName(displayName);
    setOrganisationName(org);
    if (!t) {
      router.push("/");
      return;
    }
    void Promise.allSettled([loadData(t), loadAdminProfile(t)]).catch((error: unknown) => {
      const message = error instanceof Error ? error.message : "Failed to load admin dashboard";
      setPageError(message);
    });
  }, []);

  async function loadAdminProfile(t: string) {
    try {
      const profile = await apiRequest("/admin/profile", t);
      setAdminName(String(profile?.full_name || profile?.email || "").trim());
      if (String(profile?.organisation || "").trim()) {
        setOrganisationName(String(profile.organisation).trim());
      }
    } catch {
    }
  }

  useEffect(() => {
    if (!employeeId || !token) return;
    void hydrateEmployeePermissions(employeeId);
  }, [connections]);

  useEffect(() => {
    setEmployeeCardPage(1);
  }, [employeeSearch]);

  useEffect(() => {
    if (employeeCardPage > totalEmployeeCardPages) {
      setEmployeeCardPage(totalEmployeeCardPages);
    }
  }, [employeeCardPage, totalEmployeeCardPages]);

  useEffect(() => {
    if (activeTab === "enterprise" && token) {
      void loadEnterpriseData();
    }
  }, [activeTab, token]);

  useEffect(() => {
    if (activeTab === "data-analyse" && token) {
      void loadAdminAnalysisUsage();
    }
  }, [activeTab, token]);

  async function loadData(t: string) {
    const [employeeRes, connectionRes, logsRes, metadataRes] = await Promise.allSettled([
      apiRequest("/admin/employees", t),
      apiRequest("/admin/connections", t),
      apiRequest("/admin/query-logs", t),
      apiRequest("/admin/metadata", t),
    ]);

    if (employeeRes.status === "fulfilled") {
      setEmployees(employeeRes.value);
    }
    if (connectionRes.status === "fulfilled") {
      const connectionList = connectionRes.value;
      setConnections(connectionList);
      if (connectionList.length) {
        setSchemaConnectionId((prev) => prev ?? Number(connectionList[0].id));
      } else {
        setSchemaConnectionId(null);
      }
    }
    if (logsRes.status === "fulfilled") {
      setLogs(logsRes.value);
    }
    if (metadataRes.status === "fulfilled") {
      setMetadata(metadataRes.value);
    }

    const firstFailure = [employeeRes, connectionRes, logsRes, metadataRes].find((result) => result.status === "rejected") as PromiseRejectedResult | undefined;
    if (firstFailure) {
      const message = firstFailure.reason instanceof Error ? firstFailure.reason.message : "Some dashboard data could not be refreshed.";
      setPageError(message);
    } else {
      setPageError("");
    }
  }

  async function createConnection(event: FormEvent) {
    event.preventDefault();
    try {
      const endpoint = editingConnectionId ? `/admin/connections/${editingConnectionId}` : "/admin/connections";
      const method = editingConnectionId ? "PUT" : "POST";
      await apiRequest(endpoint, token, { method, body: JSON.stringify(form) });
      setConnectionMessage(editingConnectionId ? "Connection updated successfully." : "Connection added successfully.");
      setForm({ name: "", db_type: "mysql", method: "form" });
      setEditingConnectionId(null);

      try {
        const latestConnections = await apiRequest("/admin/connections", token);
        setConnections(latestConnections);
        if (latestConnections.length) {
          setSchemaConnectionId((prev) => prev ?? Number(latestConnections[0].id));
        }
      } catch {
      }

      await loadData(token);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Connection save failed";
      setConnectionMessage(message);
    }
  }

  async function testConnection() {
    try {
      await apiRequest("/admin/connections/test", token, { method: "POST", body: JSON.stringify(form) });
      setConnectionMessage("Connection test successful.");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Connection test failed";
      setConnectionMessage(message);
    }
  }

  async function createEmployee(event: FormEvent) {
    event.preventDefault();
    
    if (!isPasswordStrong(employeeForm.password)) {
      alert("Password does not meet strength requirements. Please use a stronger password.");
      return;
    }
    
    const created = await apiRequest("/admin/employees", token, {
      method: "POST",
      body: JSON.stringify({ ...employeeForm, role: "employee" }),
    });
    setEmployeeForm({ full_name: "", email: "", position: "", password: "" });
    await loadData(token);
    if (created?.id) {
      setEmployeeId(created.id);
      await hydrateEmployeePermissions(created.id);
    }
  }

  async function hydrateEmployeePermissions(employeeIdValue: string) {
    if (!employeeIdValue) {
      setPermissionDraft({});
      return;
    }

    const assigned = await apiRequest(`/admin/employees/${employeeIdValue}/permissions`, token);
    const assignedMap: Record<number, { can_read: boolean; can_query: boolean; can_visualize: boolean; can_export: boolean; allowed_tables: string[]; all_tables: boolean }> = {};
    for (const connection of connections) {
      assignedMap[connection.id] = {
        can_read: false,
        can_query: false,
        can_visualize: false,
        can_export: false,
        allowed_tables: [],
        all_tables: true,
      };
    }
    for (const row of assigned) {
      const allowedTables = Array.isArray(row.allowed_tables) ? row.allowed_tables.filter(Boolean) : ["*"];
      const allTables = allowedTables.length === 0 || allowedTables.includes("*");
      assignedMap[row.connection_id] = {
        can_read: !!row.can_read,
        can_query: !!row.can_query,
        can_visualize: !!row.can_visualize,
        can_export: !!row.can_export,
        all_tables: allTables,
        allowed_tables: allTables ? [] : allowedTables,
      };
    }
    setPermissionDraft(assignedMap);
  }

  async function onEmployeeChange(employeeIdValue: string) {
    setEmployeeId(employeeIdValue);
    setEmployeeDetailTab("profile");
    await hydrateEmployeePermissions(employeeIdValue);
  }

  async function removeEmployee(target: { id: string; full_name?: string; email?: string }) {
    if (!target?.id) return;
    const label = target.full_name || target.email || target.id;
    const confirmed = window.confirm(`Remove employee '${label}'?`);
    if (!confirmed) return;

    setRemovingEmployeeId(target.id);
    try {
      await apiRequest(`/admin/employees/${target.id}`, token, { method: "DELETE" });
      if (employeeId === target.id) {
        setEmployeeId("");
        setPermissionDraft({});
      }
      await loadData(token);
      alert("Employee removed successfully");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Failed to remove employee";
      alert(message);
    } finally {
      setRemovingEmployeeId("");
    }
  }

  async function loadEnterpriseData() {
    try {
      const [auditRes, limitsRes, usageRes, scheduleRes, healthRes] = await Promise.all([
        apiRequest("/admin/audit-logs?limit=300", token),
        apiRequest("/admin/governance-limits", token),
        apiRequest("/admin/governance-usage", token),
        apiRequest("/admin/scheduled-reports", token),
        apiRequest("/admin/connection-health", token),
      ]);
      setAuditTimeline(Array.isArray(auditRes) ? auditRes : []);
      setGovernanceLimits(limitsRes || {});
      setGovernanceUsage(usageRes || null);
      setScheduledReports(Array.isArray(scheduleRes) ? scheduleRes : []);
      setConnectionHealth(Array.isArray(healthRes) ? healthRes : []);
      setScheduleConnectionIds((prev) => (prev.length ? prev : (connections || []).map((item: any) => Number(item.id)).slice(0, 1)));
      setEnterpriseMessage("");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Failed to load enterprise data";
      setEnterpriseMessage(message);
    }
  }

  async function saveGovernanceLimits(event: FormEvent) {
    event.preventDefault();
    try {
      const payload = {
        max_queries_per_employee_per_day: Number(governanceLimits.max_queries_per_employee_per_day || 0),
        max_exports_per_employee_per_day: Number(governanceLimits.max_exports_per_employee_per_day || 0),
        max_rows_per_query: Number(governanceLimits.max_rows_per_query || 0),
      };
      await apiRequest("/admin/governance-limits", token, { method: "PUT", body: JSON.stringify(payload) });
      setEnterpriseMessage("Governance limits updated");
      await loadEnterpriseData();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Failed to save governance limits";
      setEnterpriseMessage(message);
    }
  }

  async function createScheduledReport(event: FormEvent) {
    event.preventDefault();
    if (!scheduleConnectionIds.length) {
      setEnterpriseMessage("Select at least one connection in Scheduled Reports before creating.");
      return;
    }
    try {
      await apiRequest("/admin/scheduled-reports", token, {
        method: "POST",
        body: JSON.stringify({
          ...reportForm,
          format: reportForm.format,
          interval_minutes: Number(reportForm.interval_minutes),
          connection_ids: scheduleConnectionIds,
        }),
      });
      setEnterpriseMessage("Scheduled report created. It is saved in the table below. Use Run Now to execute immediately.");
      setReportForm({ name: "", prompt: "", format: "csv", interval_minutes: 60, recipient_email: "" });
      await loadEnterpriseData();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Failed to create scheduled report";
      setEnterpriseMessage(message);
    }
  }

  function applySchedulePreset(mode: "daily" | "weekly" | "monthly") {
    if (mode === "daily") {
      setReportForm((prev) => ({
        ...prev,
        name: "Daily Business Summary",
        interval_minutes: 1440,
        prompt: "Give me today's top KPIs, trend changes, and anomalies in a concise summary.",
      }));
      return;
    }
    if (mode === "weekly") {
      setReportForm((prev) => ({
        ...prev,
        name: "Weekly Performance Review",
        interval_minutes: 10080,
        prompt: "Summarize this week's performance by key metrics, regions, and product categories.",
      }));
      return;
    }
    setReportForm((prev) => ({
      ...prev,
      name: "Monthly Executive Report",
      interval_minutes: 43200,
      prompt: "Provide monthly executive insights with KPI comparisons and major movements.",
    }));
  }

  function toggleScheduleConnection(connectionId: number) {
    setScheduleConnectionIds((prev) =>
      prev.includes(connectionId) ? prev.filter((id) => id !== connectionId) : [...prev, connectionId]
    );
  }

  async function runScheduledReport(reportId: number) {
    try {
      const blob = await apiRequest(`/admin/scheduled-reports/${reportId}/run`, token, { method: "POST" });
      const url = URL.createObjectURL(blob as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `scheduled-report-${reportId}`;
      link.click();
      URL.revokeObjectURL(url);
      setEnterpriseMessage("Scheduled report executed and downloaded");
      await loadEnterpriseData();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Failed to run scheduled report";
      setEnterpriseMessage(message);
    }
  }

  function togglePermission(connectionId: number, key: "can_read" | "can_query" | "can_visualize" | "can_export", nextValue: boolean) {
    setPermissionDraft((prev) => {
      const current = prev[connectionId] || { can_read: false, can_query: false, can_visualize: false, can_export: false, allowed_tables: [], all_tables: true };
      const next = { ...current, [key]: nextValue };
      if (!next.can_read) {
        next.can_query = false;
        next.can_visualize = false;
        next.can_export = false;
      }
      if ((key === "can_query" || key === "can_visualize" || key === "can_export") && nextValue) {
        next.can_read = true;
      }
      return { ...prev, [connectionId]: next };
    });
  }

  function toggleAllTables(connectionId: number, nextValue: boolean) {
    setPermissionDraft((prev) => {
      const current = prev[connectionId] || { can_read: false, can_query: false, can_visualize: false, can_export: false, allowed_tables: [], all_tables: true };
      return {
        ...prev,
        [connectionId]: {
          ...current,
          all_tables: nextValue,
          allowed_tables: nextValue ? [] : current.allowed_tables,
        },
      };
    });
  }

  function toggleTableSelection(connectionId: number, tableName: string, nextValue: boolean) {
    setPermissionDraft((prev) => {
      const current = prev[connectionId] || { can_read: false, can_query: false, can_visualize: false, can_export: false, allowed_tables: [], all_tables: true };
      const base = new Set(current.allowed_tables || []);
      if (nextValue) {
        base.add(tableName);
      } else {
        base.delete(tableName);
      }
      const selected = Array.from(base);
      return {
        ...prev,
        [connectionId]: {
          ...current,
          all_tables: false,
          allowed_tables: selected,
        },
      };
    });
  }

  async function assignPermissions(event: FormEvent) {
    event.preventDefault();
    setPermissionAssignNotice("");
    if (!employeeId) {
      setPermissionAssignNoticeType("error");
      setPermissionAssignNotice("Select an employee first.");
      return;
    }
    const permissions = Object.entries(permissionDraft)
      .map(([connectionId, rights]) => ({ connection_id: Number(connectionId), ...rights, allowed_tables: rights.all_tables ? ["*"] : rights.allowed_tables }))
      .filter((entry) => entry.can_read);
    if (permissions.length === 0) {
      setPermissionAssignNoticeType("error");
      setPermissionAssignNotice("Select at least one connection with Read access before assigning.");
      return;
    }
    const connectionIds = permissions.map((entry) => entry.connection_id);

    setPermissionAssignLoading(true);
    setPermissionAssignNoticeType("info");
    setPermissionAssignNotice("Assigning permissions and refreshing access...");
    try {
      await apiRequest("/admin/permissions", token, {
        method: "POST",
        body: JSON.stringify({ employee_id: employeeId, connection_ids: connectionIds, permissions }),
      });
      await loadData(token);
      await hydrateEmployeePermissions(employeeId);
      setPermissionAssignNoticeType("success");
      setPermissionAssignNotice("Permissions successfully assigned and refreshed.");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Permission assignment failed";
      setPermissionAssignNoticeType("error");
      setPermissionAssignNotice(message);
    } finally {
      setPermissionAssignLoading(false);
    }
  }

  async function refreshMetadata(connectionId: number) {
    await apiRequest(`/admin/connections/${connectionId}/refresh-metadata`, token, { method: "POST" });
    const schemaRows = await apiRequest(`/admin/metadata`, token);
    setMetadata(schemaRows);
  }

  function startEditConnection(connection: any) {
    setActiveTab("add-connection");
    setEditingConnectionId(connection.id);
    setForm({
      name: connection.name,
      db_type: connection.db_type,
      method: connection.connection_url ? "url" : "form",
      host: connection.host || "",
      port: connection.port || undefined,
      username: connection.username || "",
      database_name: connection.database_name || "",
      connection_url: connection.connection_url || "",
      password: "",
    });
    setConnectionMessage(`Editing connection #${connection.id}`);
  }

  async function deleteConnection(connectionId: number) {
    await apiRequest(`/admin/connections/${connectionId}`, token, { method: "DELETE" });
    await loadData(token);
  }

  function toggleAnalysisConnection(connectionId: number) {
    setAnalysisConnectionIds((prev) =>
      prev.includes(connectionId) ? prev.filter((id) => id !== connectionId) : [...prev, connectionId]
    );
  }

  async function runAnalysis() {
    if (isAnalysisRunning) {
      return;
    }
    setAnalysisError("");
    setAnalysisRedirectNotice("");
    setAnalysisRows([]);
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
      setAnalysisError("Enter a prompt");
      return;
    }
    const selectedConnectionSnapshot = [...analysisConnectionIds];
    setAnalysisSelectionSnapshot(selectedConnectionSnapshot);

   let spinnerDelayTimer: ReturnType<typeof setTimeout> | null = null;

setIsAnalysisRunning(true);

spinnerDelayTimer = setTimeout(() => {
  setShowAnalysisBuffer(true);
}, 220);
    try {
      const data = await apiRequest("/admin/analyse", token, {
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
              source: "admin.analytics-studio",
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

      setAnalysisRows(data.rows || []);
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
      await loadAdminAnalysisUsage();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Analysis failed";
      setAnalysisError(message);
      setAnalysisRedirectNotice("");
      setAgenticTrace(null);
      setAnalysisRows([]);
      setGeneratedQueries([]);
      setGenerationInfo(null);
      setOverview("");
      setAnalytics(null);
      setDuration(0);
      setZeroRowReason("");
      await loadAdminAnalysisUsage();
    } finally {
      if (spinnerDelayTimer) {
        window.clearTimeout(spinnerDelayTimer);
      }
      setShowAnalysisBuffer(false);
      setIsAnalysisRunning(false);
    }
  }

  async function exportAnalysis(formatType: "csv" | "excel" | "pdf") {
    setAnalysisError("");
    if (!analysisPrompt.trim() || !analysisConnectionIds.length) {
      setAnalysisError("Select at least one connection and enter a prompt before download");
      return;
    }
    try {
      const blob = await apiRequest(`/admin/analyse/export/${formatType}`, token, {
        method: "POST",
        body: JSON.stringify({ prompt: analysisPrompt, connection_ids: analysisConnectionIds }),
        headers: { "Content-Type": "application/json" },
      });
      const url = URL.createObjectURL(blob as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `admin-analysis.${formatType === "excel" ? "xlsx" : formatType}`;
      link.click();
      URL.revokeObjectURL(url);
      await loadAdminAnalysisUsage();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Export failed";
      setAnalysisError(message);
      await loadAdminAnalysisUsage();
    }
  }

  async function loadAdminAnalysisUsage() {
    try {
      const usage = await apiRequest("/admin/analysis-usage", token);
      setAdminAnalysisUsage(usage);
    } catch {
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

  function getUsageBand(used: number, limit: number) {
    const safeLimit = limit > 0 ? limit : 1;
    const ratio = used / safeLimit;
    if (ratio >= 0.9) {
      return {
        rowClass: "bg-red-50",
        indicatorClass: "bg-red-500",
      };
    }
    if (ratio >= 0.7) {
      return {
        rowClass: "bg-yellow-100/70",
        indicatorClass: "bg-yellow-500",
      };
    }
    if (ratio >= 0.4) {
      return {
        rowClass: "bg-amber-50",
        indicatorClass: "bg-amber-400",
      };
    }
    return {
      rowClass: "bg-emerald-50/60",
      indicatorClass: "bg-emerald-500",
    };
  }

  function formatEmployeeDisplay(employeeIdValue: string) {
    const employee = employeeById[String(employeeIdValue)] || null;
    if (!employee) return employeeIdValue || "-";
    const fullName = String(employee.full_name || "").trim();
    const email = String(employee.email || "").trim();
    if (fullName && email) return `${fullName} (${email})`;
    return fullName || email || employeeIdValue || "-";
  }

  return (
    <main className="admin-console-shell role-theme role-admin page-stagger min-h-screen bg-gradient-to-br from-slate-100 via-blue-50 to-indigo-100 p-4 md:p-8">
      <div className="w-full max-w-[96rem] mx-auto space-y-6">
      <header className="space-y-3 bg-white/90 border border-slate-200 rounded-2xl p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-2">
            <Image src="/expo_logo-removebg-preview.png" alt="Ask Data" width={240} height={240} priority className="h-auto w-[200px] sm:w-[220px]" />
            <h1 className="text-3xl font-bold tracking-tight text-slate-900">Admin Console</h1>
            <p className="text-sm font-medium text-slate-600">Manage users, data sources, schema catalog, and analytics from one workspace.</p>
            <div className="flex flex-wrap items-center gap-2 text-xs md:text-sm">
              <HoverGuide text="Shows the signed-in admin profile for this workspace.">
                <span className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 font-semibold text-sky-800">
                  Admin: {adminName || "-"}
                </span>
              </HoverGuide>
              <HoverGuide text="Shows the active tenant organisation currently managed in this console.">
                <span className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 font-semibold text-blue-800">
                  Organisation: {organisationName || "-"}
                </span>
              </HoverGuide>
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
        {pageError && pageError.trim().toLowerCase() !== "admin only" && <p className="text-sm text-red-600">{pageError}</p>}
      </header>

      <div className="space-y-4">
        <section className="bg-white/90 border border-slate-200 p-4 rounded-2xl shadow-sm">
          <p className="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-3">Modules</p>
          <div className="module-bar">
            <HoverGuide text="Create employee accounts and manage login-ready user records.">
              <button onClick={() => setActiveTab("employee-add")} className={`module-tab text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "employee-add" ? "is-active" : ""}`}>User Management</button>
            </HoverGuide>
            <HoverGuide text="Assign and update per-employee access permissions for each data source.">
              <button onClick={() => setActiveTab("access-control")} className={`module-tab text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "access-control" ? "is-active" : ""}`}>Access Control</button>
            </HoverGuide>
            <HoverGuide text="Register, edit, and maintain database connections used by employees.">
              <button onClick={() => setActiveTab("add-connection")} className={`module-tab text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "add-connection" ? "is-active" : ""}`}>Data Sources</button>
            </HoverGuide>
            <HoverGuide text="Explore table structures and relationships for connected systems.">
              <button onClick={() => setActiveTab("schema")} className={`module-tab text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "schema" ? "is-active" : ""}`}>Schema Catalog</button>
            </HoverGuide>
            <HoverGuide text="Run natural-language analytics queries and inspect generated insights.">
              <button onClick={() => setActiveTab("data-analyse")} className={`module-tab text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "data-analyse" ? "is-active" : ""}`}>Analytics Studio</button>
            </HoverGuide>
            <HoverGuide text="Review policy, audit, and governance activity for enterprise control.">
              <button onClick={() => setActiveTab("enterprise")} className={`module-tab text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "enterprise" ? "is-active" : ""}`}>Enterprise Governance</button>
            </HoverGuide>
          </div>
        </section>

        <div className="space-y-6">

      {activeTab === "employee-add" && (
        <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4">
          <h2 className="font-semibold">User Management</h2>
          <form className="grid grid-cols-1 md:grid-cols-2 gap-3" onSubmit={createEmployee}>
            <input className="border p-2 rounded" placeholder="Full Name" value={employeeForm.full_name} onChange={(e) => setEmployeeForm({ ...employeeForm, full_name: e.target.value })} required />
            <input className="border p-2 rounded" placeholder="Email" value={employeeForm.email} onChange={(e) => setEmployeeForm({ ...employeeForm, email: e.target.value })} required />
            <input className="border p-2 rounded md:col-span-2" placeholder="Position (e.g., Data Analyst, BI Engineer)" value={employeeForm.position} onChange={(e) => setEmployeeForm({ ...employeeForm, position: e.target.value })} required />
            <div className="md:col-span-2 space-y-2">
              <div className="flex border rounded overflow-hidden">
                <input
                  className="w-full p-2 outline-none"
                  type={showEmployeePassword ? "text" : "password"}
                  placeholder="Temporary Password"
                  value={employeeForm.password}
                  onChange={(e) => {
                    setEmployeeForm({ ...employeeForm, password: e.target.value });
                    setShowEmployeePasswordStrength(e.target.value.length > 0);
                  }}
                  required
                />
                <button
                  type="button"
                  className="px-3 text-sm text-slate-700 bg-slate-100 hover:bg-slate-200"
                  onClick={() => setShowEmployeePassword((prev) => !prev)}
                >
                  {showEmployeePassword ? "Hide" : "Show"}
                </button>
              </div>
              {showEmployeePasswordStrength && <PasswordStrengthMeter strength={employeePasswordStrength} />}
            </div>
            <button className="bg-indigo-600 text-white rounded-lg p-2.5 col-span-1 md:col-span-2">Create Employee</button>
          </form>

          <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
            Employee access rights are managed in the dedicated Access Control tab.
            <button type="button" onClick={() => setActiveTab("access-control")} className="ml-2 underline font-semibold">Go to Access Control</button>
          </div>
        </section>
      )}

      {activeTab === "access-control" && (
        <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4">
          <h2 className="font-semibold">Access Control</h2>
          <div className="space-y-2">
            <input
              className="w-full border rounded p-2"
              placeholder="Search employee by name, email, or position"
              value={employeeSearch}
              onChange={(e) => setEmployeeSearch(e.target.value)}
            />
            {!employeeSearch.trim() && (
              <p className="text-xs text-slate-500">Showing 6 employees per page. Use search to find specific employees quickly.</p>
            )}
          </div>

          <div className="stagger-grid grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {visibleEmployeeCards.map((employee) => (
              <button
                key={employee.id}
                type="button"
                onClick={() => onEmployeeChange(employee.id)}
                className={`text-left rounded-xl border p-3 transition-colors ${employeeId === employee.id ? "border-blue-500 bg-blue-50" : "border-slate-200 bg-slate-50 hover:bg-slate-100"}`}
              >
                <p className="font-semibold text-slate-900">{employee.full_name}</p>
                <p className="text-sm text-slate-600">{employee.email}</p>
                <p className="mt-2 text-xs text-slate-600">Position: {employee.position || "-"}</p>
              </button>
            ))}
          </div>
          {visibleEmployeeCards.length === 0 && <p className="text-sm text-slate-600">No employee found for this search.</p>}

          {filteredEmployees.length > employeeCardsPerPage && (
            <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
              <span className="text-slate-600">Page {employeeCardPage} of {totalEmployeeCardPages}</span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setEmployeeCardPage((prev) => Math.max(1, prev - 1))}
                  disabled={employeeCardPage <= 1}
                  className="rounded-md bg-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-800 disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  type="button"
                  onClick={() => setEmployeeCardPage((prev) => Math.min(totalEmployeeCardPages, prev + 1))}
                  disabled={employeeCardPage >= totalEmployeeCardPages}
                  className="rounded-md bg-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-800 disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}

          <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-4">
            <div className="flex items-center justify-between gap-2">
              <h3 className="font-semibold text-slate-900">Employee Details</h3>
              {selectedEmployee && (
                <div className="flex gap-2 items-center">
                  <button
                    type="button"
                    onClick={() => setEmployeeDetailTab("profile")}
                    className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${employeeDetailTab === "profile" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}
                  >
                    Profile
                  </button>
                  <button
                    type="button"
                    onClick={() => setEmployeeDetailTab("assign-permission")}
                    className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${employeeDetailTab === "assign-permission" ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-700"}`}
                  >
                    Assign Permission
                  </button>
                  <button
                    type="button"
                    onClick={() => removeEmployee(selectedEmployee)}
                    disabled={removingEmployeeId === selectedEmployee.id}
                    className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
                  >
                    {removingEmployeeId === selectedEmployee.id ? "Removing..." : "Remove Employee"}
                  </button>
                </div>
              )}
            </div>

            {!selectedEmployee && <p className="text-sm text-slate-600">Select an employee card to view profile and assign permissions.</p>}

            {selectedEmployee && employeeDetailTab === "profile" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <span className="text-slate-500">Name</span>
                  <p className="font-semibold text-slate-900">{selectedEmployee.full_name}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <span className="text-slate-500">Email</span>
                  <p className="font-semibold text-slate-900">{selectedEmployee.email}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <span className="text-slate-500">Position</span>
                  <p className="font-semibold text-slate-900">{selectedEmployee.position || "-"}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <span className="text-slate-500">Role</span>
                  <p className="font-semibold text-slate-900">{selectedEmployee.role}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <span className="text-slate-500">Department</span>
                  <p className="font-semibold text-slate-900">{selectedEmployee.department || "-"}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <span className="text-slate-500">Phone</span>
                  <p className="font-semibold text-slate-900">{selectedEmployee.phone || "-"}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <span className="text-slate-500">Manager Name</span>
                  <p className="font-semibold text-slate-900">{selectedEmployee.manager_name || "-"}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <span className="text-slate-500">Location</span>
                  <p className="font-semibold text-slate-900">{selectedEmployee.location || "-"}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <span className="text-slate-500">Timezone</span>
                  <p className="font-semibold text-slate-900">{selectedEmployee.timezone || "-"}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                  <span className="text-slate-500">Preferred Language</span>
                  <p className="font-semibold text-slate-900">{selectedEmployee.preferred_language || "-"}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 md:col-span-2">
                  <span className="text-slate-500">Bio</span>
                  <p className="font-semibold text-slate-900 whitespace-pre-wrap">{selectedEmployee.bio || "-"}</p>
                </div>
              </div>
            )}

            {selectedEmployee && employeeDetailTab === "assign-permission" && (
              <form className="grid grid-cols-1 gap-3" onSubmit={assignPermissions}>
                <div className="border p-2 rounded text-sm text-slate-600">
                  Managing access for {selectedEmployee.full_name}
                </div>
                {permissionAssignNotice && (
                  <div
                    className={`rounded-lg border px-3 py-2 text-sm font-medium ${
                      permissionAssignNoticeType === "success"
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                        : permissionAssignNoticeType === "error"
                          ? "border-red-200 bg-red-50 text-red-700"
                          : "border-blue-200 bg-blue-50 text-blue-700"
                    }`}
                  >
                    {permissionAssignNotice}
                  </div>
                )}
                {permissionAssignLoading && (
                  <div className="rounded-lg border border-blue-200 bg-blue-50 p-2">
                    <div className="h-2 w-full overflow-hidden rounded-full bg-blue-100">
                      <div className="h-full w-2/3 animate-pulse rounded-full bg-blue-500" />
                    </div>
                  </div>
                )}
                <div className="overflow-auto border rounded">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left border-b">
                        <th className="p-2">Connection</th>
                        <th className="p-2">Read</th>
                        <th className="p-2">Query</th>
                        <th className="p-2">Visualize</th>
                        <th className="p-2">Export</th>
                        <th className="p-2">Table Access</th>
                      </tr>
                    </thead>
                    <tbody>
                      {connections.map((connection) => {
                        const rights = permissionDraft[connection.id] || { can_read: false, can_query: false, can_visualize: false, can_export: false, allowed_tables: [], all_tables: true };
                        const tableOptions = tableOptionsByConnection[connection.id] || [];
                        return (
                          <tr key={connection.id} className="border-b">
                            <td className="p-2">#{connection.id} {connection.name}</td>
                            <td className="p-2"><input type="checkbox" checked={rights.can_read} onChange={(e) => togglePermission(connection.id, "can_read", e.target.checked)} /></td>
                            <td className="p-2"><input type="checkbox" checked={rights.can_query} onChange={(e) => togglePermission(connection.id, "can_query", e.target.checked)} /></td>
                            <td className="p-2"><input type="checkbox" checked={rights.can_visualize} onChange={(e) => togglePermission(connection.id, "can_visualize", e.target.checked)} /></td>
                            <td className="p-2"><input type="checkbox" checked={rights.can_export} onChange={(e) => togglePermission(connection.id, "can_export", e.target.checked)} /></td>
                            <td className="p-2 min-w-[260px]">
                              <details className="rounded border border-slate-200 bg-slate-50 p-2">
                                <summary className="cursor-pointer text-xs font-semibold text-slate-700">
                                  {rights.all_tables ? "All Tables" : `${rights.allowed_tables.length} table(s) selected`}
                                </summary>
                                <div className="mt-2 space-y-1 max-h-40 overflow-auto">
                                  <label className="flex items-center gap-2 text-xs font-semibold text-slate-700">
                                    <input
                                      type="checkbox"
                                      checked={rights.all_tables}
                                      onChange={(e) => toggleAllTables(connection.id, e.target.checked)}
                                    />
                                    All Tables
                                  </label>
                                  {tableOptions.map((tableName) => (
                                    <label key={`${connection.id}-${tableName}`} className="flex items-center gap-2 text-xs text-slate-700">
                                      <input
                                        type="checkbox"
                                        checked={rights.all_tables ? true : rights.allowed_tables.includes(tableName)}
                                        disabled={rights.all_tables}
                                        onChange={(e) => toggleTableSelection(connection.id, tableName, e.target.checked)}
                                      />
                                      <span>{tableName}</span>
                                    </label>
                                  ))}
                                  {tableOptions.length === 0 && <p className="text-xs text-slate-500">No metadata tables found for this connection.</p>}
                                </div>
                              </details>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <button
                  disabled={permissionAssignLoading}
                  className="rounded-lg bg-emerald-600 p-2.5 text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {permissionAssignLoading ? "Assigning..." : "Assign Permissions"}
                </button>
              </form>
            )}
          </div>
        </section>
      )}

      {activeTab === "add-connection" && (
        <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4">
          <h2 className="font-semibold">Data Source Management</h2>
          {connectionMessage && <p className="text-sm rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-700 font-medium">{connectionMessage}</p>}

          <form className="grid grid-cols-1 md:grid-cols-2 gap-3" onSubmit={createConnection}>
            <input className="border p-2 rounded" placeholder="Name" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
            <select className="border p-2 rounded" value={form.db_type} onChange={(e) => setForm({ ...form, db_type: e.target.value })}>
              <option value="mysql">MySQL</option>
              <option value="postgresql">PostgreSQL</option>
              <option value="mongodb">MongoDB</option>
            </select>

            <select className="border p-2 rounded" value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}>
              <option value="form">Form</option>
              <option value="url">URL</option>
            </select>

            {form.method === "url" ? (
              <>
                <input className="border p-2 rounded col-span-2" placeholder="Connection URL" value={form.connection_url || ""} onChange={(e) => setForm({ ...form, connection_url: e.target.value })} required />
                {form.db_type === "mongodb" && (
                  <input
                    className="border p-2 rounded col-span-2"
                    placeholder="Database Name"
                    value={form.database_name || ""}
                    onChange={(e) => setForm({ ...form, database_name: e.target.value })}
                    required
                  />
                )}
              </>
            ) : (
              <>
                <input className="border p-2 rounded" placeholder="Host" value={form.host || ""} onChange={(e) => setForm({ ...form, host: e.target.value })} />
                <input className="border p-2 rounded" placeholder="Port" type="number" value={form.port || ""} onChange={(e) => setForm({ ...form, port: Number(e.target.value) })} />
                <input className="border p-2 rounded" placeholder="Username" value={form.username || ""} onChange={(e) => setForm({ ...form, username: e.target.value })} />
                <input className="border p-2 rounded" placeholder="Password" type="password" value={form.password || ""} onChange={(e) => setForm({ ...form, password: e.target.value })} />
                <input className="border p-2 rounded col-span-2" placeholder="Database Name" value={form.database_name || ""} onChange={(e) => setForm({ ...form, database_name: e.target.value })} />
              </>
            )}

            <div className="col-span-1 md:col-span-2 flex gap-2 flex-wrap">
              <button type="button" onClick={testConnection} className="bg-slate-700 text-white rounded-lg px-4 py-2">Test Connection</button>
              <button className="bg-blue-600 text-white rounded-lg px-4 py-2">{editingConnectionId ? "Update Connection" : "Add Connection"}</button>
              {editingConnectionId && (
                <button
                  type="button"
                  onClick={() => {
                    setEditingConnectionId(null);
                    setForm({ name: "", db_type: "mysql", method: "form" });
                    setConnectionMessage("");
                  }}
                  className="bg-slate-200 text-slate-800 rounded-lg px-4 py-2"
                >
                  Cancel Edit
                </button>
              )}
            </div>
          </form>

          <div className="overflow-auto rounded-lg border border-slate-200">
            <table className="w-full text-sm mt-2">
              <thead>
                <tr className="text-left border-b"><th>Name</th><th>Type</th><th>Host/URL</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {connections.map((connection) => (
                  <tr key={connection.id} className="border-b">
                    <td>{connection.name}</td>
                    <td>{connection.db_type}</td>
                    <td>{connection.connection_url || connection.host || "-"}</td>
                    <td className="py-1">
                      <div className="flex gap-2">
                        <button type="button" onClick={() => startEditConnection(connection)} className="bg-amber-500 text-white rounded-md px-3 py-1.5 text-xs">Update</button>
                        <button type="button" onClick={() => deleteConnection(connection.id)} className="bg-red-600 text-white rounded-md px-3 py-1.5 text-xs">Delete</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {activeTab === "schema" && (
        <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4 overflow-auto">
          <h2 className="font-semibold">Schema Catalog</h2>
          <div className="flex flex-wrap items-center gap-2">
            <HoverGuide text="Choose the connection whose schema you want to inspect and visualize." align="left">
              <select
                className="border rounded p-2 text-sm"
                value={schemaConnectionId ?? ""}
                onChange={(e) => setSchemaConnectionId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="" disabled>Select Connection</option>
                {connections.map((connection) => (
                  <option key={connection.id} value={connection.id}>#{connection.id} {connection.name} ({connection.db_type})</option>
                ))}
              </select>
            </HoverGuide>
            {schemaConnectionId !== null && (
              <HoverGuide text="Fetches the latest table and column metadata from the selected source.">
                <button onClick={() => refreshMetadata(schemaConnectionId)} className="bg-indigo-600 text-white rounded px-3 py-2 text-sm">Refresh Metadata</button>
              </HoverGuide>
            )}
          </div>

          {filteredSchemaRows.length > 0 ? (
            <div className="space-y-4">
              <div>
                <HoverGuide text="Graph view of entities and PK/FK links for quick schema understanding." align="left">
                  <h3 className="text-sm font-semibold text-slate-700 mb-2">Entity Relationship Diagram</h3>
                </HoverGuide>
                <SchemaERDiagram rows={filteredSchemaRows} />
              </div>

              <div>
                <h3 className="text-sm font-semibold text-slate-700 mb-2">Schema Table View</h3>
                <table className="w-full text-sm mt-2">
                  <thead>
                    <tr className="text-left border-b"><th>Table</th><th>Column</th><th>Type</th><th>Relation</th></tr>
                  </thead>
                  <tbody>
                    {filteredSchemaRows.map((item) => (
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
            <p className="text-sm text-slate-600">No schema metadata available for the selected connection.</p>
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
              {analysisError && <p className="text-red-600 text-sm font-medium">{analysisError}</p>}
              {!analysisError && generatedQueries.length === 0 && agenticTrace?.intent?.name === "non-analytics" && (
                <p className="rounded-xl border border-amber-300 bg-amber-50/90 px-3 py-2 text-amber-800 text-sm font-medium">
                  Non-analytics prompt: no SQL generated.
                </p>
              )}
              {!analysisError && analysisRows.length === 0 && generatedQueries.length > 0 && zeroRowReason && (
                <p className="text-amber-700 text-sm font-medium">No rows reason: {zeroRowReason}</p>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {connections.map((connection) => (
                <label key={connection.id} className={`flex items-center justify-between gap-2 border rounded-xl p-3 text-sm transition-colors ${analysisConnectionIds.includes(connection.id) ? "border-blue-300 bg-blue-50" : "border-slate-200 bg-slate-50 hover:bg-slate-100"}`}>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={analysisConnectionIds.includes(connection.id)}
                      onChange={() => toggleAnalysisConnection(connection.id)}
                    />
                    <span className="font-medium">#{connection.id} {connection.name}</span>
                  </div>
                  <span className="text-xs font-semibold text-slate-500 uppercase">{connection.db_type}</span>
                </label>
              ))}
            </div>
            {connections.length === 0 && <p className="text-sm text-slate-600">No assigned connections available for analysis.</p>}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><p className="text-slate-500">Selected</p><p className="font-semibold">{analysisConnectionIds.length}</p></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><p className="text-slate-500">Rows</p><p className="font-semibold">{analysisRows.length}</p></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><p className="text-slate-500">Time</p><p className="font-semibold">{duration ? `${duration.toFixed(3)}s` : "-"}</p></div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"><p className="text-slate-500">Generated</p><p className="font-semibold">{generatedQueries.length}</p></div>
            </div>
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
                      {analysisError ? <p className="text-sm text-red-600">Current issue: {analysisError}</p> : null}
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
                          <p className="text-xs text-slate-600">Row cap: {agenticTrace?.connections?.[0]?.policy?.max_rows ?? adminAnalysisUsage?.limits?.max_rows_per_query ?? "-"}</p>
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
                    rowCount={analysisRows.length}
                    errorMessage={analysisError}
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
                  {!analysisRows.length && <p className="text-sm text-slate-600">Run analysis first to enable downloads.</p>}
                  {analysisRows.length > 0 && !canExportSelected && <p className="text-sm text-amber-700">Export access is disabled for one or more selected sources.</p>}
                  {analysisRows.length > 0 && canExportSelected && (
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
                  {!analysisRows.length && <p className="text-sm text-slate-600">Run analysis first to visualize data.</p>}
                  {analysisRows.length > 0 && !canVisualizeSelected && <p className="text-sm text-amber-700">Visualization access is disabled for one or more selected sources.</p>}
                  {analysisRows.length > 0 && canVisualizeSelected && (
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
                          {analysisColumns.map((column) => (
                            <option key={column} value={column}>{column}</option>
                          ))}
                        </select>
                        <select className="border rounded px-2 py-1" value={valueFeature} onChange={(e) => setValueFeature(e.target.value)}>
                          {analysisColumns.map((column) => (
                            <option key={column} value={column}>{column}</option>
                          ))}
                        </select>
                      </div>
                      <ResultChart rows={analysisRows} chartType={chartType} labelKey={labelFeature} valueKey={valueFeature} />
                    </>
                  )}
                </>
              )}

              {studioPanel === "results" && (
                <>
                  <h2 className="font-semibold">Results</h2>
                  {!analysisRows.length && <p className="text-sm text-slate-600">Run analysis to view result rows.</p>}
                  {analysisRows.length > 0 && (
                    <table className="w-full text-sm">
                      <thead>
                        <tr>
                          {Object.keys(analysisRows[0]).map((key) => (
                            <th key={key} className="text-left border-b p-1">{key}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {analysisRows.map((row, rowIndex) => (
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

      {activeTab === "enterprise" && (
        <section className="space-y-4">
          <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">Enterprise Governance</h2>
              <button onClick={loadEnterpriseData} className="bg-slate-700 text-white rounded-lg px-4 py-2 text-sm">Refresh</button>
            </div>
            {enterpriseMessage && <p className="text-sm text-slate-700">{enterpriseMessage}</p>}
          </section>

          <section className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)] gap-4">
            <aside className="bg-white/90 border border-slate-200 p-4 rounded-2xl shadow-sm h-fit">
              <p className="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-3">Enterprise Tabs</p>
              <div className="flex lg:flex-col gap-2 flex-wrap">
                <button onClick={() => setEnterpriseTab("governance")} className={`text-left px-3 py-2 rounded-lg text-sm font-semibold ${enterpriseTab === "governance" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Governance Usage</button>
                <button onClick={() => setEnterpriseTab("schedules")} className={`text-left px-3 py-2 rounded-lg text-sm font-semibold ${enterpriseTab === "schedules" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Scheduled Reports</button>
                <button onClick={() => setEnterpriseTab("health")} className={`text-left px-3 py-2 rounded-lg text-sm font-semibold ${enterpriseTab === "health" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Connection Health</button>
                <button onClick={() => setEnterpriseTab("audit")} className={`text-left px-3 py-2 rounded-lg text-sm font-semibold ${enterpriseTab === "audit" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700"}`}>Audit Timeline</button>
              </div>
            </aside>

            <div className="space-y-4">
              {enterpriseTab === "governance" && (
                <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm space-y-3">
                  <h3 className="font-semibold">Governance Usage (Today)</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                    <div className="rounded border border-slate-200 bg-slate-50 p-3">
                      <p className="text-slate-600">Query Limit Per Employee</p>
                      <p className="font-semibold text-slate-900">{governanceUsage?.limits?.max_queries_per_employee_per_day ?? governanceLimits.max_queries_per_employee_per_day ?? "-"}</p>
                    </div>
                    <div className="rounded border border-slate-200 bg-slate-50 p-3">
                      <p className="text-slate-600">Export Limit Per Employee</p>
                      <p className="font-semibold text-slate-900">{governanceUsage?.limits?.max_exports_per_employee_per_day ?? governanceLimits.max_exports_per_employee_per_day ?? "-"}</p>
                    </div>
                    <div className="rounded border border-slate-200 bg-slate-50 p-3">
                      <p className="text-slate-600">Max Rows Per Query</p>
                      <p className="font-semibold text-slate-900">{governanceUsage?.limits?.max_rows_per_query ?? governanceLimits.max_rows_per_query ?? "-"}</p>
                    </div>
                  </div>
                  <div className="overflow-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left border-b"><th>Employee</th><th>Email</th><th>Queries</th><th>Exports</th></tr>
                      </thead>
                      <tbody>
                        {(governanceUsage?.employees || []).map((item: any) => {
                          const queryBand = getUsageBand(Number(item.queries_today || 0), Number(item.query_limit || 0));
                          const exportBand = getUsageBand(Number(item.exports_today || 0), Number(item.export_limit || 0));
                          return (
                            <tr key={item.employee_id} className={`border-b ${queryBand.rowClass}`}>
                              <td>{item.full_name || item.employee_id}</td>
                              <td>{item.email || "-"}</td>
                              <td>
                                <div className="flex items-center gap-2">
                                  <span>{item.queries_today} / {item.query_limit}</span>
                                  <span className={`h-2.5 w-2.5 rounded-full ${queryBand.indicatorClass}`} aria-hidden="true"></span>
                                </div>
                              </td>
                              <td>
                                <div className="flex items-center gap-2">
                                  <span>{item.exports_today} / {item.export_limit}</span>
                                  <span className={`h-2.5 w-2.5 rounded-full ${exportBand.indicatorClass}`} aria-hidden="true"></span>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {enterpriseTab === "schedules" && (
                <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm space-y-3">
                  <h3 className="font-semibold">Scheduled Reports</h3>
                  <div className="flex flex-wrap gap-2">
                    <span className="text-sm text-slate-600">Simple Mode:</span>
                    <button type="button" onClick={() => applySchedulePreset("daily")} className="rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700">Daily</button>
                    <button type="button" onClick={() => applySchedulePreset("weekly")} className="rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700">Weekly</button>
                    <button type="button" onClick={() => applySchedulePreset("monthly")} className="rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700">Monthly</button>
                  </div>
                  <form className="grid grid-cols-1 md:grid-cols-2 gap-3" onSubmit={createScheduledReport}>
                    <div className="space-y-1">
                      <label className="text-sm font-medium text-slate-700">Report Name</label>
                      <input className="w-full border p-2 rounded" placeholder="Report Name" value={reportForm.name} onChange={(e) => setReportForm((prev) => ({ ...prev, name: e.target.value }))} required />
                    </div>
                    <div className="space-y-1">
                      <label className="text-sm font-medium text-slate-700">Recipient Email</label>
                      <input className="w-full border p-2 rounded" placeholder="Recipient Email" type="email" value={reportForm.recipient_email} onChange={(e) => setReportForm((prev) => ({ ...prev, recipient_email: e.target.value }))} required />
                    </div>
                    <div className="space-y-1">
                      <label className="text-sm font-medium text-slate-700">Report Format</label>
                      <select className="w-full border p-2 rounded" value={reportForm.format} onChange={(e) => setReportForm((prev) => ({ ...prev, format: e.target.value }))}>
                        <option value="csv">CSV</option>
                        <option value="pdf">PDF</option>
                      </select>
                    </div>
                    <div className="space-y-1">
                      <label className="text-sm font-medium text-slate-700">Interval (minutes)</label>
                      <input className="w-full border p-2 rounded" type="number" min={5} value={reportForm.interval_minutes} onChange={(e) => setReportForm((prev) => ({ ...prev, interval_minutes: Number(e.target.value) }))} placeholder="Interval (minutes)" required />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <label className="text-sm font-medium text-slate-700">Connections To Include</label>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 rounded border border-slate-200 p-3">
                        {connections.map((connection) => (
                          <label key={connection.id} className="inline-flex items-center gap-2 text-sm">
                            <input type="checkbox" checked={scheduleConnectionIds.includes(connection.id)} onChange={() => toggleScheduleConnection(connection.id)} />
                            <span>#{connection.id} {connection.name} ({connection.db_type})</span>
                          </label>
                        ))}
                      </div>
                    </div>
                    <div className="space-y-1 md:col-span-2">
                      <label className="text-sm font-medium text-slate-700">Report Prompt</label>
                      <textarea className="w-full border p-2 rounded" placeholder="Report prompt" value={reportForm.prompt} onChange={(e) => setReportForm((prev) => ({ ...prev, prompt: e.target.value }))} required />
                    </div>
                    <button className="bg-emerald-600 text-white rounded-lg p-2.5 md:col-span-2">Create Scheduled Report</button>
                  </form>
                  <p className="text-xs text-slate-500">Creating a schedule saves it for repeated use. To run immediately, click Run Now in the table.</p>
                  <div className="overflow-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left border-b"><th>ID</th><th>Name</th><th>Format</th><th>Last Status</th><th>Last Run</th><th>Action</th></tr>
                      </thead>
                      <tbody>
                        {scheduledReports.map((row) => (
                          <tr key={row.id} className="border-b">
                            <td>{row.report_id}</td>
                            <td>{row.name}</td>
                            <td>{row.format}</td>
                            <td>{row.last_status || "-"}</td>
                            <td>{row.last_run_at ? new Date(row.last_run_at).toLocaleString() : "-"}</td>
                            <td><button onClick={() => runScheduledReport(Number(row.report_id))} className="bg-slate-700 text-white rounded px-3 py-1.5 text-xs">Run Now</button></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {enterpriseTab === "health" && (
                <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm space-y-3">
                  <h3 className="font-semibold">Connection Health</h3>
                  <div className="overflow-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left border-b"><th>Connection</th><th>Type</th><th>Status</th><th>Detail</th><th>Checked At</th></tr>
                      </thead>
                      <tbody>
                        {connectionHealth.map((item) => (
                          <tr key={`${item.connection_id}-${item.connection_name}`} className="border-b">
                            <td>#{item.connection_id} {item.connection_name}</td>
                            <td>{item.db_type}</td>
                            <td className={item.status === "healthy" ? "text-emerald-700" : "text-red-700"}>{item.status}</td>
                            <td>{item.detail}</td>
                            <td>{item.checked_at ? new Date(item.checked_at).toLocaleString() : "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {enterpriseTab === "audit" && (
                <section className="bg-white/90 border border-slate-200 p-5 rounded-2xl shadow-sm space-y-3">
                  <h3 className="font-semibold">Audit Timeline</h3>
                  <div className="overflow-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left border-b"><th>Time</th><th>Actor</th><th>Action</th><th>Target</th></tr>
                      </thead>
                      <tbody>
                        {auditTimeline.map((item) => (
                          <tr key={item.id} className="border-b">
                            <td>{item.created_at ? new Date(item.created_at).toLocaleString() : "-"}</td>
                            <td>{item.actor_user_id} ({item.actor_role})</td>
                            <td>{item.action}</td>
                            <td>{item.target_type}:{item.target_id}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </div>
          </section>
        </section>
      )}
        </div>
      </div>
      </div>
    </main>
  );
}
