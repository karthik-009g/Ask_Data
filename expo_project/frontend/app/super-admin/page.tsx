"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { apiRequest } from "../../lib/api";
import { validatePassword, isPasswordStrong } from "../../lib/passwordValidator";
import { PasswordStrengthMeter } from "../../components/PasswordStrengthMeter";

type OrganisationMetric = {
  organisation: string;
  admin_count: number;
  employee_count: number;
  database_count: number;
};

type MetricsResponse = {
  admin_count: number;
  organisation_count: number;
  organisations: OrganisationMetric[];
};

type AdminCredential = {
  id: string;
  full_name: string;
  email: string;
  role: string;
  created_at?: string;
};

type OrganisationDatabase = {
  connection_id: number;
  name: string;
  db_type: string;
  database_name?: string;
  host?: string;
  created_at?: string;
};

type OrganisationDetails = {
  organisation: string;
  admin_credentials: AdminCredential[];
  employee_count: number;
  database_count: number;
  databases: OrganisationDatabase[];
};

function parseJwt(token: string): Record<string, any> {
  try {
    const payload = token.split(".")[1];
    return JSON.parse(atob(payload));
  } catch {
    return {};
  }
}

export default function SuperAdminPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [organisationSearch, setOrganisationSearch] = useState("");
  const [selectedOrganisation, setSelectedOrganisation] = useState("");
  const [organisationDetails, setOrganisationDetails] = useState<OrganisationDetails | null>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [removingOrg, setRemovingOrg] = useState(false);
  const [removingAdminId, setRemovingAdminId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [globalHealth, setGlobalHealth] = useState<any[]>([]);
  const [targetGovernanceOrg, setTargetGovernanceOrg] = useState("");
  const [activeTab, setActiveTab] = useState<"organisations" | "admin" | "enterprise">("organisations");
  const [enterpriseTab, setEnterpriseTab] = useState<"governance" | "health" | "audit">("governance");
  const [governanceFeedback, setGovernanceFeedback] = useState("");
  const [healthOrgSearch, setHealthOrgSearch] = useState("");
  const [healthSelectedOrg, setHealthSelectedOrg] = useState("");
  const [governanceLimits, setGovernanceLimits] = useState({
    max_queries_per_employee_per_day: 200,
    max_exports_per_employee_per_day: 30,
    max_rows_per_query: 500,
  });

  const [adminForm, setAdminForm] = useState({
    organisation: "",
    full_name: "",
    email: "",
    password: "",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showStrength, setShowStrength] = useState(false);
  const strength = validatePassword(adminForm.password);
  const visibleOrganisations = useMemo(() => {
    const all = metrics?.organisations || [];
    const query = organisationSearch.trim().toLowerCase();
    if (query) {
      return all.filter((org) => org.organisation.toLowerCase().includes(query));
    }
    return all.slice(0, 6);
  }, [metrics, organisationSearch]);
  const healthOrgOptions = useMemo(() => {
    const unique = Array.from(
      new Set(
        globalHealth
          .map((item) => String(item.organisation || "").trim().toLowerCase())
          .filter(Boolean)
      )
    ).sort();
    const query = healthOrgSearch.trim().toLowerCase();
    if (!query) return unique;
    return unique.filter((org) => org.includes(query));
  }, [globalHealth, healthOrgSearch]);
  const filteredHealthRows = useMemo(() => {
    const selected = healthSelectedOrg.trim().toLowerCase();
    const query = healthOrgSearch.trim().toLowerCase();
    if (selected) {
      return globalHealth.filter((item) => String(item.organisation || "").trim().toLowerCase() === selected);
    }
    if (query) {
      return globalHealth.filter((item) => String(item.organisation || "").trim().toLowerCase().includes(query));
    }
    return globalHealth;
  }, [globalHealth, healthSelectedOrg, healthOrgSearch]);

  useEffect(() => {
    const t = localStorage.getItem("token") || "";
    setToken(t);
    if (!t) {
      router.push("/");
      return;
    }
    const payload = parseJwt(t);
    if (payload.role !== "super_admin") {
      router.push("/");
      return;
    }
    void refreshMetrics(t);
    void loadEnterprisePanels(t);
  }, []);

  async function loadEnterprisePanels(currentToken: string) {
    try {
      const [auditRows, healthRows] = await Promise.all([
        apiRequest("/super-admin/audit-logs?limit=400", currentToken),
        apiRequest("/super-admin/connection-health", currentToken),
      ]);
      setAuditLogs(Array.isArray(auditRows) ? auditRows : []);
      setGlobalHealth(Array.isArray(healthRows) ? healthRows : []);
    } catch (err: any) {
      setError(err?.message || "Failed to load enterprise control panels");
    }
  }

  async function refreshMetrics(currentToken: string) {
    try {
      const response: MetricsResponse = await apiRequest("/super-admin/metrics", currentToken);
      setMetrics(response);
      if (selectedOrganisation) {
        const exists = response.organisations.some((item) => item.organisation === selectedOrganisation);
        if (!exists) {
          setSelectedOrganisation("");
          setOrganisationDetails(null);
        }
      }
      setError("");
    } catch (err: any) {
      setError(err?.message || "Failed to load super admin metrics");
    }
  }

  async function loadOrganisationDetails(orgName: string) {
    setSelectedOrganisation(orgName);
    setHealthSelectedOrg((orgName || "").trim().toLowerCase());
    setLoadingDetails(true);
    setNotice("");
    setError("");
    try {
      const encoded = encodeURIComponent(orgName);
      const details = await apiRequest(`/super-admin/organisations/details?organisation=${encoded}`, token);
      setOrganisationDetails(details);
    } catch (err: any) {
      setError(err?.message || "Failed to load organisation details");
      setOrganisationDetails(null);
    } finally {
      setLoadingDetails(false);
    }
  }

  async function removeOrganisation() {
    if (!selectedOrganisation) return;
    const confirmed = window.confirm(`Remove organisation '${selectedOrganisation}' and all tenant data? This cannot be undone.`);
    if (!confirmed) return;

    setRemovingOrg(true);
    setNotice("");
    setError("");
    try {
      const encoded = encodeURIComponent(selectedOrganisation);
      const response = await apiRequest(`/super-admin/organisations?organisation=${encoded}`, token, { method: "DELETE" });
      setNotice(response?.message || "Organisation removed");
      setSelectedOrganisation("");
      setOrganisationDetails(null);
      await refreshMetrics(token);
    } catch (err: any) {
      setError(err?.message || "Failed to remove organisation");
    } finally {
      setRemovingOrg(false);
    }
  }

  async function removeAdmin(admin: AdminCredential) {
    if (!admin?.id) return;
    const confirmed = window.confirm(`Remove admin '${admin.full_name}' (${admin.email})?`);
    if (!confirmed) return;

    setRemovingAdminId(admin.id);
    setNotice("");
    setError("");
    try {
      const response = await apiRequest(`/super-admin/admins/${admin.id}`, token, { method: "DELETE" });
      setNotice(response?.message || "Admin removed");
      await refreshMetrics(token);
      if (selectedOrganisation) {
        await loadOrganisationDetails(selectedOrganisation);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to remove admin");
    } finally {
      setRemovingAdminId("");
    }
  }

  async function createAdmin(e: FormEvent) {
    e.preventDefault();
    setNotice("");
    setError("");

    if (!isPasswordStrong(adminForm.password)) {
      setError("Password does not meet strength requirements.");
      return;
    }

    try {
      await apiRequest("/super-admin/admins", token, {
        method: "POST",
        body: JSON.stringify({ ...adminForm, role: "admin" }),
      });
      setNotice("Admin user provisioned successfully.");
      setAdminForm({ organisation: "", full_name: "", email: "", password: "" });
      setShowStrength(false);
      await refreshMetrics(token);
    } catch (err: any) {
      setError(err?.message || "Failed to create admin");
    }
  }

  async function updateGovernanceForOrganisation(e: FormEvent) {
    e.preventDefault();
    setGovernanceFeedback("");
    if (!targetGovernanceOrg.trim()) {
      setError("Enter organisation name for governance update");
      return;
    }
    try {
      const response = await apiRequest(`/super-admin/organisations/${encodeURIComponent(targetGovernanceOrg.trim())}/governance-limits`, token, {
        method: "PUT",
        body: JSON.stringify(governanceLimits),
      });
      const message = response?.message || `Governance limits updated for ${targetGovernanceOrg.trim()}`;
      setNotice(message);
      setGovernanceFeedback(message);
    } catch (err: any) {
      const message = err?.message || "Failed to update governance limits";
      setError(message);
      setGovernanceFeedback(message);
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
    <main className="role-theme role-super-admin page-stagger min-h-screen bg-gradient-to-br from-slate-100 via-cyan-50 to-sky-100 p-4 md:p-8">
      <div className="w-full max-w-[96rem] mx-auto space-y-6">
        <header className="space-y-3 bg-white/90 border border-cyan-200 rounded-2xl p-5 shadow-md">
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-2">
              <Image src="/expo_logo-removebg-preview.png" alt="Ask Data" width={240} height={240} priority className="h-auto w-[200px] sm:w-[220px]" />
              <h1 className="text-3xl font-bold tracking-tight text-slate-900">Super Admin Control Plane</h1>
              <p className="text-sm font-medium text-slate-600">Enterprise-wide tenant and user governance.</p>
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

          <div className="stagger-grid grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
            <button
              type="button"
              onClick={() => setActiveTab("organisations")}
              className="text-left rounded-xl border border-blue-200 bg-gradient-to-br from-blue-50 to-white px-4 py-3 shadow-sm hover:shadow transition-shadow"
            >
              <p className="font-semibold text-blue-900">Organisation Management</p>
              <p className="text-xs text-slate-600 mt-1">View organisation details, admins, and databases.</p>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("admin")}
              className="text-left rounded-xl border border-cyan-200 bg-gradient-to-br from-cyan-50 to-white px-4 py-3 shadow-sm hover:shadow transition-shadow"
            >
              <p className="font-semibold text-cyan-900">Admin Provisioning</p>
              <p className="text-xs text-slate-600 mt-1">Create or remove tenant admins securely.</p>
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab("enterprise");
                setEnterpriseTab("governance");
              }}
              className="text-left rounded-xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-white px-4 py-3 shadow-sm hover:shadow transition-shadow"
            >
              <p className="font-semibold text-emerald-900">Enterprise Controls</p>
              <p className="text-xs text-slate-600 mt-1">Governance, connection status, and audit oversight.</p>
            </button>
          </div>

          <div className="flex flex-wrap gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2">
            <button onClick={() => setActiveTab("organisations")} className={`text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "organisations" ? "bg-blue-600 text-white" : "bg-white text-slate-700 hover:bg-slate-200"}`}>Organisation Management</button>
            <button onClick={() => setActiveTab("admin")} className={`text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "admin" ? "bg-blue-600 text-white" : "bg-white text-slate-700 hover:bg-slate-200"}`}>Admin Provisioning</button>
            <button onClick={() => setActiveTab("enterprise")} className={`text-left px-4 py-2.5 rounded-xl text-sm font-semibold ${activeTab === "enterprise" ? "bg-blue-600 text-white" : "bg-white text-slate-700 hover:bg-slate-200"}`}>Enterprise Controls</button>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
          {notice && <p className="text-sm text-emerald-700">{notice}</p>}

        </header>

        {activeTab === "admin" && (
          <section className="bg-white/90 border border-slate-200 rounded-2xl p-5 shadow-sm max-w-xl">
            <form onSubmit={createAdmin} className="space-y-3">
            <h2 className="font-semibold">Provision New Admin</h2>
            <input
              className="w-full border rounded p-2"
              placeholder="Organisation"
              value={adminForm.organisation}
              onChange={(e) => setAdminForm((prev) => ({ ...prev, organisation: e.target.value }))}
              required
            />
            <input
              className="w-full border rounded p-2"
              placeholder="Full Name"
              value={adminForm.full_name}
              onChange={(e) => setAdminForm((prev) => ({ ...prev, full_name: e.target.value }))}
              required
            />
            <input
              className="w-full border rounded p-2"
              placeholder="Email"
              type="email"
              value={adminForm.email}
              onChange={(e) => setAdminForm((prev) => ({ ...prev, email: e.target.value }))}
              required
            />
            <div className="space-y-2">
              <div className="flex w-full border rounded overflow-hidden">
                <input
                  className="w-full p-2 outline-none"
                  type={showPassword ? "text" : "password"}
                  placeholder="Temporary Password"
                  value={adminForm.password}
                  onChange={(e) => {
                    setAdminForm((prev) => ({ ...prev, password: e.target.value }));
                    setShowStrength(e.target.value.length > 0);
                  }}
                  required
                />
                <button
                  type="button"
                  className="px-3 text-sm text-slate-700 bg-slate-100 hover:bg-slate-200"
                  onClick={() => setShowPassword((prev) => !prev)}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
              {showStrength && <PasswordStrengthMeter strength={strength} />}
            </div>
            <button className="w-full bg-blue-600 text-white rounded-lg p-2.5">Create Admin</button>
            </form>
          </section>
        )}

        {activeTab === "organisations" && (
          <section className="bg-white/90 border border-slate-200 rounded-2xl p-5 shadow-sm overflow-auto">
            <h2 className="font-semibold mb-3">Organisations</h2>

            <div className="mb-4 space-y-2">
              <input
                className="w-full border border-slate-300 rounded-xl p-2.5"
                placeholder="Search organisation by name"
                value={organisationSearch}
                onChange={(e) => setOrganisationSearch(e.target.value)}
              />
              {!organisationSearch.trim() && (
                <p className="text-xs text-slate-500">Showing only first 6 organisations. Use search to find any organisation.</p>
              )}
            </div>

            <div className="stagger-grid grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {visibleOrganisations.map((org) => (
                <button
                  key={org.organisation}
                  type="button"
                  onClick={() => loadOrganisationDetails(org.organisation)}
                  className={`text-left rounded-xl border p-3 transition-colors shadow-sm ${selectedOrganisation === org.organisation ? "border-blue-500 bg-blue-50" : "border-slate-200 bg-slate-50 hover:bg-slate-100"}`}
                >
                  <p className="font-semibold text-slate-900">{org.organisation}</p>
                  <div className="mt-2 text-xs text-slate-600 space-y-1">
                    <p>Admins: {org.admin_count}</p>
                    <p>Employees: {org.employee_count}</p>
                    <p>Databases: {org.database_count}</p>
                  </div>
                </button>
              ))}
            </div>
            {visibleOrganisations.length === 0 && <p className="mt-3 text-sm text-slate-600">No organisation found for this search.</p>}

            <div className="mt-5 rounded-xl border border-slate-200 bg-white p-4 space-y-4">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-semibold text-slate-900">Organisation Details</h3>
                {selectedOrganisation && (
                  <button
                    type="button"
                    onClick={removeOrganisation}
                    disabled={removingOrg}
                    className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60"
                  >
                    {removingOrg ? "Removing..." : "Remove Organisation"}
                  </button>
                )}
              </div>

              {!selectedOrganisation && <p className="text-sm text-slate-600">Click an organisation box to view all details.</p>}
              {loadingDetails && <p className="text-sm text-slate-600">Loading organisation details...</p>}

              {!loadingDetails && organisationDetails && (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                      <span className="text-slate-600">Organisation</span>
                      <p className="font-semibold text-slate-900">{organisationDetails.organisation}</p>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                      <span className="text-slate-600">Employees</span>
                      <p className="font-semibold text-slate-900">{organisationDetails.employee_count}</p>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                      <span className="text-slate-600">Databases</span>
                      <p className="font-semibold text-slate-900">{organisationDetails.database_count}</p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold text-slate-800">Admin Credentials (No Password)</h4>
                    {organisationDetails.admin_credentials.length === 0 ? (
                      <p className="text-sm text-slate-600">No admins found.</p>
                    ) : (
                      <div className="overflow-auto rounded-lg border border-slate-200">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-left border-b bg-slate-50">
                              <th className="p-2">Name</th>
                              <th className="p-2">Email</th>
                              <th className="p-2">Role</th>
                              <th className="p-2">Created At</th>
                              <th className="p-2">Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {organisationDetails.admin_credentials.map((admin) => (
                              <tr key={admin.id} className="border-b">
                                <td className="p-2">{admin.full_name}</td>
                                <td className="p-2">{admin.email}</td>
                                <td className="p-2">{admin.role}</td>
                                <td className="p-2">{admin.created_at ? new Date(admin.created_at).toLocaleString() : "-"}</td>
                                <td className="p-2">
                                  <button
                                    type="button"
                                    onClick={() => removeAdmin(admin)}
                                    disabled={removingAdminId === admin.id}
                                    className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                                  >
                                    {removingAdminId === admin.id ? "Removing..." : "Remove"}
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold text-slate-800">Databases</h4>
                    {organisationDetails.databases.length === 0 ? (
                      <p className="text-sm text-slate-600">No databases configured.</p>
                    ) : (
                      <div className="overflow-auto rounded-lg border border-slate-200">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-left border-b bg-slate-50">
                              <th className="p-2">ID</th>
                              <th className="p-2">Name</th>
                              <th className="p-2">Type</th>
                              <th className="p-2">Database</th>
                              <th className="p-2">Host</th>
                            </tr>
                          </thead>
                          <tbody>
                            {organisationDetails.databases.map((db) => (
                              <tr key={`${db.connection_id}-${db.name}`} className="border-b">
                                <td className="p-2">{db.connection_id}</td>
                                <td className="p-2">{db.name}</td>
                                <td className="p-2">{db.db_type}</td>
                                <td className="p-2">{db.database_name || "-"}</td>
                                <td className="p-2">{db.host || "-"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {activeTab === "enterprise" && (
        <section className="bg-white/90 border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold">Enterprise Controls</h2>
            <button className="rounded-lg bg-slate-700 px-4 py-2 text-sm font-semibold text-white" onClick={() => loadEnterprisePanels(token)}>Refresh Panels</button>
          </div>

          <div className="space-y-4">
            <div className="flex flex-wrap gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2">
              <button onClick={() => setEnterpriseTab("governance")} className={`rounded px-3 py-2 text-sm font-semibold ${enterpriseTab === "governance" ? "bg-blue-600 text-white" : "bg-white text-slate-700"}`}>Governance</button>
              <button onClick={() => setEnterpriseTab("health")} className={`rounded px-3 py-2 text-sm font-semibold ${enterpriseTab === "health" ? "bg-blue-600 text-white" : "bg-white text-slate-700"}`}>Connection Health</button>
              <button onClick={() => setEnterpriseTab("audit")} className={`rounded px-3 py-2 text-sm font-semibold ${enterpriseTab === "audit" ? "bg-blue-600 text-white" : "bg-white text-slate-700"}`}>Audit</button>
            </div>

            <div>
              {enterpriseTab === "governance" && (
                <section className="rounded-xl border border-slate-200 p-4 space-y-2">
                  <h3 className="font-semibold text-slate-900">Organisation Governance</h3>
                  <form className="grid grid-cols-1 gap-2" onSubmit={updateGovernanceForOrganisation}>
                    <label className="text-sm font-medium text-slate-700">Organisation</label>
                    <input className="border rounded p-2" placeholder="Organisation" value={targetGovernanceOrg} onChange={(e) => setTargetGovernanceOrg(e.target.value)} required />

                    <label className="text-sm font-medium text-slate-700">Max Queries Per Employee Per Day</label>
                    <input className="border rounded p-2" type="number" min={1} value={governanceLimits.max_queries_per_employee_per_day} onChange={(e) => setGovernanceLimits((prev) => ({ ...prev, max_queries_per_employee_per_day: Number(e.target.value) }))} required />

                    <label className="text-sm font-medium text-slate-700">Max Exports Per Employee Per Day</label>
                    <input className="border rounded p-2" type="number" min={1} value={governanceLimits.max_exports_per_employee_per_day} onChange={(e) => setGovernanceLimits((prev) => ({ ...prev, max_exports_per_employee_per_day: Number(e.target.value) }))} required />

                    <label className="text-sm font-medium text-slate-700">Max Rows Per Query Result</label>
                    <input className="border rounded p-2" type="number" min={1} value={governanceLimits.max_rows_per_query} onChange={(e) => setGovernanceLimits((prev) => ({ ...prev, max_rows_per_query: Number(e.target.value) }))} required />

                    <button className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white">Update Governance</button>
                    {governanceFeedback && <p className="text-sm text-slate-700">{governanceFeedback}</p>}
                  </form>
                </section>
              )}

              {enterpriseTab === "health" && (
                <section className="rounded-xl border border-slate-200 p-4 space-y-2">
                  <h3 className="font-semibold text-slate-900">Global Connection Health</h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    <input
                      className="border rounded p-2"
                      placeholder="Search organisation"
                      value={healthOrgSearch}
                      onChange={(e) => {
                        setHealthOrgSearch(e.target.value);
                        setHealthSelectedOrg("");
                      }}
                    />
                    <select
                      className="border rounded p-2"
                      value={healthSelectedOrg}
                      onChange={(e) => setHealthSelectedOrg(e.target.value)}
                    >
                      <option value="">Select Organisation</option>
                      {healthOrgOptions.map((org) => (
                        <option key={org} value={org}>{org}</option>
                      ))}
                    </select>
                  </div>
                  {!healthSelectedOrg && !healthOrgSearch.trim() && <p className="text-sm text-slate-600">Type in search or select an organisation to filter results.</p>}
                  <div className="overflow-auto max-h-72">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left border-b bg-slate-50">
                          <th className="p-2">Organisation</th>
                          <th className="p-2">Connection</th>
                          <th className="p-2">Type</th>
                          <th className="p-2">Status</th>
                          <th className="p-2">Detail</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredHealthRows.map((item, index) => (
                          <tr key={`${item.organisation}-${item.connection_id}-${index}`} className="border-b">
                            <td className="p-2">{item.organisation}</td>
                            <td className="p-2">#{item.connection_id} {item.connection_name}</td>
                            <td className="p-2">{item.db_type}</td>
                            <td className={`p-2 ${item.status === "healthy" ? "text-emerald-700" : "text-red-700"}`}>{item.status}</td>
                            <td className="p-2">{item.detail}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {enterpriseTab === "audit" && (
                <section className="rounded-xl border border-slate-200 p-4 space-y-2">
                  <h3 className="font-semibold text-slate-900">Audit Timeline</h3>
                  <div className="overflow-auto max-h-72">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left border-b bg-slate-50">
                          <th className="p-2">Time</th>
                          <th className="p-2">Organisation</th>
                          <th className="p-2">Actor</th>
                          <th className="p-2">Action</th>
                          <th className="p-2">Target</th>
                        </tr>
                      </thead>
                      <tbody>
                        {auditLogs.map((item) => (
                          <tr key={item.id} className="border-b">
                            <td className="p-2">{item.created_at ? new Date(item.created_at).toLocaleString() : "-"}</td>
                            <td className="p-2">{item.organisation || "-"}</td>
                            <td className="p-2">{item.actor_user_id} ({item.actor_role})</td>
                            <td className="p-2">{item.action}</td>
                            <td className="p-2">{item.target_type}:{item.target_id}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </div>
          </div>
        </section>
        )}
      </div>
    </main>
  );
}
