"use client";

import { FormEvent, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { apiRequest } from "../lib/api";

function parseJwt(token: string): any {
  try {
    const payload = token.split(".")[1];
    return JSON.parse(atob(payload));
  } catch {
    return {};
  }
}

export default function LoginPage() {
  const router = useRouter();
  const [organisation, setOrganisation] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [role, setRole] = useState<"super_admin" | "admin" | "employee">("admin");
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    const loginOrganisation = role === "super_admin" ? "" : organisation;
    try {
      const data = await apiRequest("/auth/login", undefined, {
        method: "POST",
        body: JSON.stringify({ organisation: loginOrganisation, email, password }),
      });
      const payload = parseJwt(data.access_token);
      if (payload.role !== role) {
        setError(`Selected role is ${role}, but this account is ${payload.role}.`);
        return;
      }
      localStorage.setItem("token", data.access_token);
      if (role === "super_admin") router.push("/super-admin");
      else if (role === "admin") router.push("/admin");
      else router.push("/employee");
    } catch (err: any) {
      setError(err.message || "Login failed");
    }
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-amber-50 via-slate-50 to-cyan-50 p-4 md:p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
          <Image src="/expo_logo-removebg-preview.png" alt="Ask Data" width={240} height={240} priority className="h-auto w-[200px] sm:w-[220px]" />
          <button
            type="button"
            onClick={() => {
              const loginSection = document.getElementById("login-panel");
              loginSection?.scrollIntoView({ behavior: "smooth", block: "center" });
            }}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
          >
            Login
          </button>
        </header>

        <section className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <div className="space-y-4 rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-100 via-orange-50 to-white p-6 shadow-sm md:p-8">
            <p className="inline-flex rounded-full border border-amber-300 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-wide text-amber-800">
              Enterprise Data Intelligence
            </p>
            <h1 className="text-3xl font-black tracking-tight text-slate-900 md:text-5xl">
              Ask Questions. Control Access. Ship Insight Faster.
            </h1>
            <p className="max-w-2xl text-sm leading-relaxed text-slate-700 md:text-base">
              Unified workspace for super-admin governance, admin orchestration, and employee self-service analytics.
              Built for secure multi-tenant data operations with approval workflows, audit timelines, connection health checks,
              and governed query limits.
            </p>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-sm font-semibold text-slate-900">Approval-First Access</p>
                <p className="mt-1 text-xs text-slate-600">Permission assignments can be reviewed and approved centrally before they go live.</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-sm font-semibold text-slate-900">Full Audit Trace</p>
                <p className="mt-1 text-xs text-slate-600">Track who changed what, when, and where across organisations and users.</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-sm font-semibold text-slate-900">Connection Reliability</p>
                <p className="mt-1 text-xs text-slate-600">Monitor health status of data sources and detect failures quickly.</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-sm font-semibold text-slate-900">Governed Usage</p>
                <p className="mt-1 text-xs text-slate-600">Enforce per-day query/export limits and row caps for safe operations.</p>
              </div>
            </div>
          </div>

          <form id="login-panel" onSubmit={onSubmit} className="h-fit rounded-2xl border border-slate-200 bg-white p-7 shadow-sm space-y-4">
            <div className="space-y-1">
              <h2 className="text-2xl font-bold text-slate-900">Welcome back</h2>
              <p className="text-sm text-slate-600">Login to your workspace with the right role context.</p>
            </div>
            {role !== "super_admin" && (
              <>
                <label className="block text-sm font-medium text-slate-700">Organisation Name (optional)</label>
                <input className="w-full border rounded p-2" placeholder="Needed only if your email exists in multiple organisations" value={organisation} onChange={(e) => setOrganisation(e.target.value)} />
              </>
            )}
            <select className="w-full border rounded p-2" value={role} onChange={(e) => setRole(e.target.value as "super_admin" | "admin" | "employee")}> 
              <option value="super_admin">Super Admin</option>
              <option value="admin">Admin</option>
              <option value="employee">Employee</option>
            </select>
            <input className="w-full border rounded p-2" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            <div className="flex w-full border rounded overflow-hidden">
              <input
                className="w-full p-2 outline-none"
                type={showPassword ? "text" : "password"}
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
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
            {error && <p className="text-red-600 text-sm">{error}</p>}
            <button className="w-full bg-blue-600 text-white rounded-lg p-2.5 font-semibold" type="submit">Login</button>
            <p className="text-xs text-center text-slate-500">Admin onboarding is managed by super admin provisioning.</p>
          </form>
        </section>
      </div>
    </main>
  );
}
